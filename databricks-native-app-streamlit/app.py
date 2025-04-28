import os
import json
import time
import threading
import queue
import datetime
from typing import Dict, List, Optional, Tuple
import pandas as pd
import streamlit as st
from databricks import sql
from databricks.sdk.core import Config
from model_serving_utils import query_endpoint
from collections import deque
import traceback
import plotly.express as px
import random
from kafka_utils import KafkaConsumer, KafkaProducer
import math

# Set page config at the beginning of the file, before any other Streamlit commands
st.set_page_config(
    page_title="Databricks Sentiment Analysis Dashboard",
    page_icon="📊",
    layout="wide",
)

# Ensure environment variables are set correctly
assert os.getenv('DATABRICKS_WAREHOUSE_ID'), "DATABRICKS_WAREHOUSE_ID must be set in app.yaml."
assert os.getenv('KAFKA_BOOTSTRAP_SERVERS'), "KAFKA_BOOTSTRAP_SERVERS must be set in app.yaml."
assert os.getenv('KAFKA_INPUT_TOPIC'), "KAFKA_INPUT_TOPIC must be set in app.yaml."
assert os.getenv('KAFKA_OUTPUT_TOPIC'), "KAFKA_OUTPUT_TOPIC must be set in app.yaml."
assert os.getenv('KAFKA_GROUP_ID'), "KAFKA_GROUP_ID must be set in app.yaml."
assert os.getenv('DATABRICKS_MODEL_ENDPOINT'), "DATABRICKS_MODEL_ENDPOINT must be set in app.yaml."

# Global variables
message_queue = queue.Queue(maxsize=100)
kafka_consumer = None  # Will be initialized in main()
kafka_producer = None  # Will be initialized in main()
# Global variables for background threads to use
thread_processed_messages = []
thread_latency_history = deque(maxlen=10000)
thread_sentiment_history = deque(maxlen=10000)
thread_message_timestamps = deque(maxlen=6000)  # Store actual message creation/receive timestamps if needed
# Queue for sending completion timestamps from worker to main thread
timestamp_queue = queue.Queue()

# Thread lock for synchronization (primarily for non-queue shared data if any remain)
thread_lock = threading.Lock()

# Initialize Streamlit session state for persistence across reruns
if 'processed_messages' not in st.session_state:
    st.session_state.processed_messages = []
if 'latency_history' not in st.session_state:
    st.session_state.latency_history = []
if 'sentiment_history' not in st.session_state:
    st.session_state.sentiment_history = []
if 'message_timestamps' not in st.session_state:
    st.session_state.message_timestamps = []
# Store processing completion timestamps in session state
if 'processing_timestamps' not in st.session_state:
    st.session_state.processing_timestamps = []
if 'current_throughput' not in st.session_state:
    st.session_state.current_throughput = 0  # Messages per minute


def sql_query(query: str) -> pd.DataFrame:
    cfg = Config()  # Pull environment variables for auth
    with sql.connect(
        server_hostname=cfg.host,
        http_path=f"/sql/1.0/warehouses/{os.getenv('DATABRICKS_WAREHOUSE_ID')}",
        credentials_provider=lambda: cfg.authenticate
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query)
            return cursor.fetchall_arrow().to_pandas()

def write_to_delta_table(df: pd.DataFrame, table_name: str):
    """Write DataFrame to a Delta table"""
    cfg = Config()
    with sql.connect(
        server_hostname=cfg.host,
        http_path=f"/sql/1.0/warehouses/{os.getenv('DATABRICKS_WAREHOUSE_ID')}",
        credentials_provider=lambda: cfg.authenticate
    ) as connection:
        with connection.cursor() as cursor:
            # Create the table if it doesn't exist
            create_table_query = f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                message_id STRING,
                original_text STRING,
                processed_timestamp TIMESTAMP,
                sentiment_score DOUBLE,
                sentiment_label STRING,
                processing_time_ms DOUBLE,
                scenario STRING,
                persona STRUCT<age: INT, profession: STRING, cultural_background: STRING>
            )
            """
            try:
                cursor.execute(create_table_query)
                print(f"Created or verified table {table_name}")
            except Exception as e:
                print(f"Error creating table: {e}")
            
            # Insert data into the table
            for _, row in df.iterrows():
                # Extract persona data
                persona = row.get('persona', {})
                age = persona.get('age', 0) if isinstance(persona, dict) else 0
                profession = persona.get('profession', '') if isinstance(persona, dict) else ''
                cultural_background = persona.get('cultural_background', '') if isinstance(persona, dict) else ''
                
                # Use a simpler approach with individual columns
                insert_query = f"""
                INSERT INTO {table_name} 
                VALUES (
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    NAMED_STRUCT('age', CAST(? AS INT), 'profession', ?, 'cultural_background', ?)
                )
                """
                
                params = (
                    row['message_id'],
                    row['original_text'],
                    row['processed_timestamp'],
                    row['sentiment_score'],
                    row['sentiment_label'],
                    row['processing_time_ms'],
                    row.get('scenario', ''),
                    age,
                    profession,
                    cultural_background
                )
                
                try:
                    cursor.execute(insert_query, params)
                except Exception as e:
                    print(f"Error inserting row: {e}")
                    print(f"Row data: {row}")
                    print(f"Params: {params}")

def get_current_throughput():
    """Calculate current throughput by counting messages in the last 60 seconds"""
    global thread_message_timestamps
    
    current_time = time.time()
    one_minute_ago = current_time - 60
    
    # Count messages with timestamps in the last 60 seconds from thread data
    recent_messages = [ts for ts in thread_message_timestamps if ts > one_minute_ago]
    message_count = len(recent_messages)
    
    # Also check session state timestamps if available
    if hasattr(st.session_state, 'message_timestamps') and st.session_state.message_timestamps:
        session_recent_messages = [ts for ts in st.session_state.message_timestamps if ts > one_minute_ago]
        if len(session_recent_messages) > message_count:
            message_count = len(session_recent_messages)
    
    print(f"Throughput: {message_count} messages in the last 60 seconds")
    return message_count

def process_message(message):
    """Process a message through sentiment analysis"""
    global thread_latency_history, thread_sentiment_history, thread_processed_messages, thread_message_timestamps
    start_time = time.time()
    
    print(f"Processing message: {message}")
    
    # Extract the text and other fields from the customer review message
    # The Lambda produces messages with this structure:
    # {
    #     "id": review_id,
    #     "text": review_text,
    #     "sentiment": sentiment,
    #     "scenario": scenario,
    #     "timestamp": timestamp,
    #     "source": "lambda_generator",
    #     "persona": {
    #         "age": persona["age"],
    #         "profession": persona["profession"],
    #         "cultural_background": persona["cultural_background"]
    #     }
    # }
    
    text = message.get('text', '')
    message_id = message.get('id', str(time.time()))
    create_time_str = message.get('timestamp')
    create_time = start_time  # Default to current time
    
    # Parse ISO timestamp if available
    if create_time_str:
        try:
            create_time = datetime.datetime.fromisoformat(create_time_str).timestamp()
        except (ValueError, TypeError):
            print(f"Could not parse timestamp: {create_time_str}, using current time")
    
    # Always analyze sentiment using the model
    # Prepare messages for the model
    messages = [
        {"role": "system", "content": "You are a sentiment analysis assistant. Analyze the sentiment of the text and respond with a single JSON object containing: sentiment_label (positive, negative, or neutral) and sentiment_score (a float between -1 and 1, where -1 is very negative, 0 is neutral, and 1 is very positive)."},
        {"role": "user", "content": f"Analyze the sentiment of this text: {text}"}
    ]
    
    # Call the model endpoint
    try:
        print(f"Calling model endpoint: bedrock-claude-haiku")
        response = query_endpoint("bedrock-claude-haiku", messages, 500)
        print(f"Model response: {response}")
        content = response.get('content', '')
        
        # Extract JSON from the response
        start_idx = content.find('{')
        end_idx = content.rfind('}') + 1
        if start_idx >= 0 and end_idx > 0:
            json_content = content[start_idx:end_idx]
            result = json.loads(json_content)
            print(f"Parsed sentiment result: {result}")
        else:
            # Fallback if JSON parsing fails
            print(f"Failed to parse JSON from content: {content}")
            result = {
                'sentiment_label': 'unknown',
                'sentiment_score': 0.0
            }
    except Exception as e:
        error_details = traceback.format_exc()
        print(f"Error in sentiment analysis: {e}")
        print(f"Detailed error: {error_details}")
        result = {
            'sentiment_label': 'error',
            'sentiment_score': 0.0
        }
    
    # Calculate processing time
    end_time = time.time()
    processing_time_ms = (end_time - start_time) * 1000
    
    # Calculate total latency (from message creation to completion)
    total_latency_ms = (end_time - create_time) * 1000
    
    # Create the processed message
    processed_message = {
        'message_id': message_id,
        'original_text': text,
        'processed_timestamp': datetime.datetime.now().isoformat(),
        'sentiment_score': result.get('sentiment_score', 0.0),
        'sentiment_label': result.get('sentiment_label', 'unknown'),
        'processing_time_ms': processing_time_ms,
        'total_latency_ms': total_latency_ms
    }
    
    # Add additional customer review fields if available
    if 'scenario' in message:
        processed_message['scenario'] = message['scenario']
    if 'persona' in message:
        processed_message['persona'] = message['persona']
    
    print(f"Created processed message: {processed_message}")
    
    # Update metrics - use thread-safe global variables
    thread_latency_history.append(total_latency_ms)
    print(f"Latency history: {list(thread_latency_history)[-5:]}")
    thread_sentiment_history.append(result.get('sentiment_score', 0.0))
    print(f"Sentiment history: {list(thread_sentiment_history)[-5:]}")
    
    # At the end of processing, record the completion timestamp
    completion_time = time.time()
    timestamp_queue.put(completion_time)
    print(f"process_message: Put timestamp {completion_time:.2f} onto queue. Approx queue size: {timestamp_queue.qsize()}")

    return processed_message

def load_data_from_warehouse():
    """Load processed messages and metrics from Databricks warehouse table"""
    global thread_message_timestamps
    
    try:
        # Query the latest data from the sentiment_analysis_results table
        query = """
        SELECT * FROM sentiment_analysis_results 
        ORDER BY processed_timestamp DESC 
        LIMIT 1000
        """
        try:
            df = sql_query(query)
            print(f"Successfully queried sentiment_analysis_results table, found {len(df)} rows")
        except Exception as e:
            print(f"Error querying sentiment_analysis_results table: {e}")
            print(traceback.format_exc())
            # Try to create the table
            try:
                create_query = """
                CREATE TABLE IF NOT EXISTS sentiment_analysis_results (
                    message_id STRING,
                    original_text STRING,
                    processed_timestamp TIMESTAMP,
                    sentiment_score DOUBLE,
                    sentiment_label STRING,
                    processing_time_ms DOUBLE,
                    scenario STRING,
                    persona STRUCT<age: INT, profession: STRING, cultural_background: STRING>
                )
                USING DELTA
                """
                cfg = Config()
                with sql.connect(
                    server_hostname=cfg.host,
                    http_path=f"/sql/1.0/warehouses/{os.getenv('DATABRICKS_WAREHOUSE_ID')}",
                    credentials_provider=lambda: cfg.authenticate
                ) as connection:
                    with connection.cursor() as cursor:
                        cursor.execute(create_query)
                print("Created sentiment_analysis_results table")
            except Exception as create_error:
                print(f"Error creating table: {create_error}")
            
            # Return empty data
            return {
                'processed_messages': [],
                'latency_history': [],
                'sentiment_history': [], 
                'message_timestamps': []
            }
        
        if df.empty:
            return {
                'processed_messages': [],
                'latency_history': [],
                'sentiment_history': [], 
                'message_timestamps': []
            }
        
        # Convert DataFrame to list of dictionaries for messages
        processed_messages = df.to_dict('records')
        
        # Extract latency values
        latency_history = df['processing_time_ms'].tolist()
        
        # Extract sentiment scores
        sentiment_history = df['sentiment_score'].tolist()
        
        # Calculate timestamps for throughput calculation
        # Convert timestamps to unix time for throughput calculation
        timestamps = []
        current_time = time.time()
        one_minute_ago = current_time - 60
        recent_count = 0
        
        for ts_str in df['processed_timestamp']:
            try:
                dt = datetime.datetime.fromisoformat(ts_str)
                unix_ts = dt.timestamp()  # Use float timestamp instead of integer
                timestamps.append(unix_ts)
                
                # For recent messages (within last minute), also add to data structures
                if unix_ts > one_minute_ago:
                    recent_count += 1
                    with thread_lock:
                        if unix_ts not in thread_message_timestamps:
                            thread_message_timestamps.append(unix_ts)
            except (ValueError, TypeError):
                continue
        
        # Log information about timestamps
        print(f"Loaded {len(timestamps)} timestamps from warehouse, {recent_count} from last 60 seconds")
        
        return {
            'processed_messages': processed_messages,
            'latency_history': latency_history,
            'sentiment_history': sentiment_history,
            'message_timestamps': timestamps
        }
    except Exception as e:
        print(f"Error loading data from warehouse: {e}")
        print(traceback.format_exc())
        return {
            'processed_messages': [],
            'latency_history': [],
            'sentiment_history': [],
            'message_timestamps': []
        }

def process_messages_thread():
    """Background thread to process messages from the queue"""
    global kafka_producer, thread_processed_messages, thread_message_timestamps, thread_latency_history, thread_sentiment_history
    
    batch = []
    last_batch_time = time.time()
    last_flush_time = time.time()
    
    while kafka_consumer.running:
        try:
            # Periodically flush the producer to ensure messages are sent
            current_time = time.time()
            if current_time - last_flush_time > 2:  # Flush every 2 seconds
                kafka_producer.flush(timeout=5)
                last_flush_time = current_time
                
            # Get message from queue with timeout
            try:
                message = message_queue.get(timeout=1.0)
                print(f"Got message from queue: {message}")
            except queue.Empty:
                # If it's been more than 10 seconds since the last batch and we have messages, process them
                if batch and time.time() - last_batch_time > 10:
                    if len(batch) > 0:
                        print(f"Processing batch of {len(batch)} messages")
                        df = pd.DataFrame(batch)
                        try:
                            write_to_delta_table(df, "sentiment_analysis_results")
                            print("Successfully wrote to Delta table")
                        except Exception as e:
                            # Log errors but don't use st.error in background thread
                            print(f"Error writing to Delta table: {e}")
                            print(traceback.format_exc())
                        batch = []
                        last_batch_time = time.time()
                continue
            
            # Process the message
            processed_message = process_message(message)
    
            # Update the processed messages list in thread-safe global variable
            thread_processed_messages.append(processed_message)
            print(f"Added to processed_messages, now have {len(thread_processed_messages)} messages")
            if len(thread_processed_messages) > 100:
                thread_processed_messages = thread_processed_messages[-100:]
            
            # Send to Kafka
            print(f"Sending to Kafka: {processed_message}")
            kafka_producer.send_message(processed_message)
            
            # Add to batch for Delta table
            batch.append(processed_message)
            
            # If batch size reaches 10 or more, write to Delta table
            if len(batch) >= 10:
                print(f"Processing batch of {len(batch)} messages")
                df = pd.DataFrame(batch)
                try:
                    write_to_delta_table(df, "sentiment_analysis_results")
                    print("Successfully wrote to Delta table")
                except Exception as e:
                    # Log errors but don't use st.error in background thread
                    print(f"Error writing to Delta table: {e}")
                    print(traceback.format_exc())
                batch = []
                last_batch_time = time.time()
            
            # Mark the task as done
            message_queue.task_done()
            
        except Exception as e:
            # Use print instead of st.error in background thread
            print(f"Error in message processing thread: {e}")
            print(traceback.format_exc())

def sync_thread_data_to_session_state():
    """Synchronize thread global variables (messages, latency, sentiment) to session state"""
    global thread_processed_messages, thread_latency_history, thread_sentiment_history, timestamp_queue
    
    # Use a lock to ensure thread safety when accessing the variables
    with thread_lock:
        # Debug prints
        print(f"Syncing data from thread variables: {len(thread_processed_messages)} messages, {len(thread_latency_history)} latency records")
        
        # For thread_processed_messages
        if thread_processed_messages:
            # Update and merge rather than replace to preserve session state for reruns
            for msg in thread_processed_messages:
                # Check if message already exists in session state
                if not any(m.get('message_id') == msg.get('message_id') for m in st.session_state.processed_messages):
                    st.session_state.processed_messages.append(msg)
                    
            # Limit to last 100 messages
            if len(st.session_state.processed_messages) > 100:
                st.session_state.processed_messages = st.session_state.processed_messages[-100:]
                
            print(f"Synced processed messages, session now has {len(st.session_state.processed_messages)} messages")
        
        # For deque objects, we need to extend the session state list with new items
        if thread_latency_history:
            st.session_state.latency_history.extend(thread_latency_history)
            if len(st.session_state.latency_history) > 10000:  # Match the deque maxlen
                st.session_state.latency_history = st.session_state.latency_history[-10000:]
            print(f"Synced latency history, session now has {len(st.session_state.latency_history)} records")
        
        if thread_sentiment_history:
            st.session_state.sentiment_history.extend(thread_sentiment_history)
            if len(st.session_state.sentiment_history) > 10000:  # Match the deque maxlen
                st.session_state.sentiment_history = st.session_state.sentiment_history[-10000:]
            print(f"Synced sentiment history, session now has {len(st.session_state.sentiment_history)} records")
            
        # Transfer timestamps from the global queue to session state
        transfer_count = 0
        while not timestamp_queue.empty():
            try:
                ts = timestamp_queue.get_nowait()
                st.session_state.processing_timestamps.append(ts)
                transfer_count += 1
            except queue.Empty:
                break
        
        if transfer_count > 0:
            print(f"Transferred {transfer_count} timestamps from queue to session state")

def calculate_metrics():
    """Calculate and return metrics based on session state data"""
    metrics = {
        'avg_latency_ms': 0,
        'max_latency_ms': 0,
        'avg_sentiment_score': 0,
        'throughput_per_min': 0,
        'sentiment_distribution': {'positive': 0, 'negative': 0, 'neutral': 0},
        'scenario_stats': {},
        'persona_stats': {}
    }
    
    # Process latency metrics
    if st.session_state.latency_history:
        latency_history = list(st.session_state.latency_history)
        metrics['avg_latency_ms'] = sum(latency_history) / len(latency_history)
        metrics['max_latency_ms'] = max(latency_history)
    
    # Process sentiment metrics
    if st.session_state.sentiment_history:
        sentiment_history = list(st.session_state.sentiment_history)
        metrics['avg_sentiment_score'] = sum(sentiment_history) / len(sentiment_history)
        
        # Calculate sentiment distribution
        if st.session_state.processed_messages:
            for msg in st.session_state.processed_messages:
                sentiment = msg.get('sentiment_label', 'unknown')
                if sentiment in metrics['sentiment_distribution']:
                    metrics['sentiment_distribution'][sentiment] += 1
    
    # Calculate throughput
    metrics['throughput_per_min'] = get_current_throughput()
    
    # Calculate scenario statistics
    if st.session_state.processed_messages:
        scenario_counts = {}
        scenario_sentiments = {}
        
        for msg in st.session_state.processed_messages:
            scenario = msg.get('scenario')
            if scenario:
                # Count scenarios
                scenario_counts[scenario] = scenario_counts.get(scenario, 0) + 1
                
                # Track sentiment by scenario
                if scenario not in scenario_sentiments:
                    scenario_sentiments[scenario] = []
                scenario_sentiments[scenario].append(msg.get('sentiment_score', 0))
        
        # Calculate average sentiment for each scenario
        for scenario, sentiments in scenario_sentiments.items():
            if sentiments:
                metrics['scenario_stats'][scenario] = {
                    'count': scenario_counts.get(scenario, 0),
                    'avg_sentiment': sum(sentiments) / len(sentiments)
                }
        
        # Calculate persona statistics (by age range, profession, cultural_background)
        age_groups = {'18-25': 0, '26-35': 0, '36-45': 0, '46-55': 0, '56+': 0}
        profession_counts = {}
        background_counts = {}
        
        for msg in st.session_state.processed_messages:
            persona = msg.get('persona', {})
            if isinstance(persona, dict):
                # Process age groups
                age = persona.get('age')
                if age:
                    if 18 <= age <= 25:
                        age_groups['18-25'] += 1
                    elif 26 <= age <= 35:
                        age_groups['26-35'] += 1
                    elif 36 <= age <= 45:
                        age_groups['36-45'] += 1
                    elif 46 <= age <= 55:
                        age_groups['46-55'] += 1
                    else:
                        age_groups['56+'] += 1
                
                # Process professions
                profession = persona.get('profession')
                if profession:
                    profession_counts[profession] = profession_counts.get(profession, 0) + 1
                
                # Process cultural backgrounds
                background = persona.get('cultural_background')
                if background:
                    background_counts[background] = background_counts.get(background, 0) + 1
        
        metrics['persona_stats'] = {
            'age_groups': age_groups,
            'professions': profession_counts,
            'backgrounds': background_counts
        }
    
    return metrics

def format_latency(ms):
    """Format latency in ms to be more readable"""
    if ms < 1000:
        return f"{ms:.2f} ms"
    else:
        return f"{ms/1000:.2f} s"

def display_metrics():
    """Display all metrics in a dashboard layout"""
    # Create a 3-column layout for key metrics
    col1, col2, col3 = st.columns(3)
    
    # Get calculated metrics
    current_metrics = calculate_metrics()
    
    # Display key metrics in columns
    with col1:
        st.metric("Avg Sentiment Score", f"{current_metrics.get('avg_sentiment_score', 0):.2f}")
    
    with col2:
        st.metric("Avg Processing Time", format_latency(current_metrics.get('avg_latency_ms', 0)))
    
    with col3:
        st.metric("Messages Per Minute", current_metrics.get('throughput_per_min', 0))
    
    # Create tabs for different visualizations
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["Recent Reviews", "Sentiment Analysis", "Processing Time", "Scenarios", "Demographics"])
    
    # Tab 1: Recent Messages
    with tab1:
        if st.session_state.processed_messages:
            messages_df = pd.DataFrame(st.session_state.processed_messages[-50:])
            st.subheader("Latest Processed Reviews")
            
            # Format the table to be more readable
            if not messages_df.empty:
                # Extract basic columns for display
                display_cols = ['message_id', 'original_text', 'sentiment_label', 'sentiment_score', 'processing_time_ms']
                
                # Add additional columns if available
                if 'scenario' in messages_df.columns:
                    display_cols.append('scenario')
                
                # Add persona information if available
                if 'persona' in messages_df.columns:
                    # Add columns for persona details with defaults if missing
                    messages_df['customer_age'] = messages_df['persona'].apply(
                        lambda p: p.get('age', 'N/A') if isinstance(p, dict) else 'N/A')
                    messages_df['customer_profession'] = messages_df['persona'].apply(
                        lambda p: p.get('profession', 'N/A') if isinstance(p, dict) else 'N/A')
                    messages_df['customer_background'] = messages_df['persona'].apply(
                        lambda p: p.get('cultural_background', 'N/A') if isinstance(p, dict) else 'N/A')
                    
                    display_cols.extend(['customer_age', 'customer_profession', 'customer_background'])
                
                # Format the time column
                if 'processing_time_ms' in messages_df.columns:
                    messages_df['processing_time_ms'] = messages_df['processing_time_ms'].apply(
                        lambda t: f"{t:.2f} ms")
                
                # Show the table with selected columns
                st.dataframe(messages_df[display_cols].sort_values('message_id', ascending=False),
                             use_container_width=True)
        else:
            st.info("No messages processed yet. Waiting for data...")
    
    # Tab 2: Sentiment Analysis Visualization
    with tab2:
        if st.session_state.sentiment_history:
            sentiment_df = pd.DataFrame({
                'timestamp': range(len(st.session_state.sentiment_history)),
                'sentiment': list(st.session_state.sentiment_history)
            })
            
            st.subheader("Sentiment Analysis Trend")
            
            # Create a line chart for sentiment
            fig = px.line(
                sentiment_df, 
                x='timestamp', 
                y='sentiment',
                title='Sentiment Score Over Time (Higher is More Positive)',
                labels={'timestamp': 'Time', 'sentiment': 'Sentiment Score'}
            )
            
            # Add a zero line for reference
            fig.add_hline(y=0, line_dash="dash", line_color="gray")
            
            # Set y-axis range from -1 to 1
            fig.update_yaxes(range=[-1.1, 1.1])
            
            st.plotly_chart(fig, use_container_width=True)
            
            # Add sentiment distribution chart (histogram)
            st.subheader("Sentiment Distribution")
            hist_fig = px.histogram(
                sentiment_df, 
                x='sentiment',
                nbins=20,
                title='Distribution of Sentiment Scores',
                labels={'sentiment': 'Sentiment Score', 'count': 'Frequency'}
            )
            st.plotly_chart(hist_fig, use_container_width=True)
        else:
            st.info("No sentiment data yet. Waiting for messages...")
    
    # Tab 3: Processing Time
    with tab3:
        if st.session_state.latency_history:
            latency_df = pd.DataFrame({
                'timestamp': range(len(st.session_state.latency_history)),
                'latency': list(st.session_state.latency_history)
            })
            
            st.subheader("Processing Time Trend")
            
            # Create a line chart for processing time
            fig = px.line(
                latency_df, 
                x='timestamp', 
                y='latency',
                title='Processing Time (ms) Over Time',
                labels={'timestamp': 'Time', 'latency': 'Processing Time (ms)'}
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No latency data yet. Waiting for messages...")
    
    # Tab 4: Scenarios Analysis
    with tab4:
        if st.session_state.processed_messages and any('scenario' in msg for msg in st.session_state.processed_messages):
            # Create DataFrame with scenarios
            scenario_data = [
                {
                    'scenario': msg.get('scenario', 'Unknown'),
                    'sentiment_score': msg.get('sentiment_score', 0),
                    'sentiment_label': msg.get('sentiment_label', 'unknown')
                }
                for msg in st.session_state.processed_messages 
                if 'scenario' in msg and msg.get('scenario')
            ]
            
            if scenario_data:
                scenario_df = pd.DataFrame(scenario_data)
                
                # Group by scenario and calculate average sentiment
                scenario_stats = scenario_df.groupby('scenario').agg(
                    avg_sentiment=('sentiment_score', 'mean'),
                    count=('scenario', 'count')
                ).reset_index().sort_values('count', ascending=False)
                
                st.subheader("Scenario Analysis")
                
                # Bar chart of scenarios by count
                count_fig = px.bar(
                    scenario_stats, 
                    x='scenario', 
                    y='count',
                    title='Frequency of Different Scenarios',
                    labels={'scenario': 'Scenario', 'count': 'Frequency'}
                )
                st.plotly_chart(count_fig, use_container_width=True)
                
                # Bar chart of scenarios by sentiment
                sentiment_fig = px.bar(
                    scenario_stats, 
                    x='scenario', 
                    y='avg_sentiment',
                    title='Average Sentiment by Scenario',
                    color='avg_sentiment',
                    color_continuous_scale='RdYlGn',  # Red to Yellow to Green
                    labels={'scenario': 'Scenario', 'avg_sentiment': 'Avg Sentiment Score'}
                )
                sentiment_fig.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(sentiment_fig, use_container_width=True)
                
                # Show the detailed data table
                st.subheader("Scenario Details")
                st.dataframe(scenario_stats, use_container_width=True)
            else:
                st.info("No scenario data available yet.")
        else:
            st.info("No scenario data yet. Waiting for messages with scenario information...")
    
    # Tab 5: Demographics Analysis
    with tab5:
        if st.session_state.processed_messages and any('persona' in msg for msg in st.session_state.processed_messages):
            st.subheader("Customer Demographics Analysis")
            
            # Access persona statistics from metrics
            persona_stats = current_metrics.get('persona_stats', {})
            
            # Create 2 columns for age and profession/background
            demo_col1, demo_col2 = st.columns(2)
            
            with demo_col1:
                # Age Distribution
                if persona_stats.get('age_groups'):
                    st.subheader("Age Distribution")
                    age_df = pd.DataFrame({
                        'Age Group': list(persona_stats['age_groups'].keys()),
                        'Count': list(persona_stats['age_groups'].values())
                    })
                    
                    # Create pie chart for age groups
                    age_fig = px.pie(
                        age_df,
                        values='Count',
                        names='Age Group',
                        title='Customer Age Distribution',
                        hole=0.4
                    )
                    st.plotly_chart(age_fig, use_container_width=True)
            
            with demo_col2:
                # Cultural Background Distribution (top 10)
                if persona_stats.get('backgrounds'):
                    st.subheader("Cultural Background")
                    
                    # Sort backgrounds by count and take top 10
                    sorted_backgrounds = sorted(
                        persona_stats['backgrounds'].items(),
                        key=lambda x: x[1],
                        reverse=True
                    )[:10]
                    
                    background_df = pd.DataFrame({
                        'Background': [b[0] for b in sorted_backgrounds],
                        'Count': [b[1] for b in sorted_backgrounds]
                    })
                    
                    # Create horizontal bar chart
                    bg_fig = px.bar(
                        background_df,
                        y='Background',
                        x='Count',
                        title='Top 10 Cultural Backgrounds',
                        orientation='h'
                    )
                    st.plotly_chart(bg_fig, use_container_width=True)
            
            # Profession analysis
            if persona_stats.get('professions'):
                st.subheader("Professional Background")
                
                # Sort professions by count and take top 15
                sorted_professions = sorted(
                    persona_stats['professions'].items(),
                    key=lambda x: x[1],
                    reverse=True
                )[:15]
                
                prof_df = pd.DataFrame({
                    'Profession': [p[0] for p in sorted_professions],
                    'Count': [p[1] for p in sorted_professions]
                })
                
                # Create horizontal bar chart
                prof_fig = px.bar(
                    prof_df,
                    y='Profession',
                    x='Count',
                    title='Top 15 Professions',
                    orientation='h'
                )
                st.plotly_chart(prof_fig, use_container_width=True)
                
                # Show detailed data tables if expanded
                with st.expander("Show detailed demographic data"):
                    st.subheader("Age Groups")
                    st.dataframe(pd.DataFrame({
                        'Age Group': list(persona_stats['age_groups'].keys()),
                        'Count': list(persona_stats['age_groups'].values())
                    }))
                    
                    st.subheader("All Professions")
                    prof_all_df = pd.DataFrame({
                        'Profession': list(persona_stats['professions'].keys()),
                        'Count': list(persona_stats['professions'].values())
                    }).sort_values('Count', ascending=False)
                    st.dataframe(prof_all_df)
                    
                    st.subheader("All Cultural Backgrounds")
                    bg_all_df = pd.DataFrame({
                        'Background': list(persona_stats['backgrounds'].keys()),
                        'Count': list(persona_stats['backgrounds'].values())
                    }).sort_values('Count', ascending=False)
                    st.dataframe(bg_all_df)
        else:
            st.info("No demographic data yet. Waiting for messages with persona information...")

def get_processing_throughput():
    """Calculate throughput based on completed message processing in the last 60 seconds, using session state data."""
    
    current_time = time.time()
    one_minute_ago = current_time - 60
    message_count = 0
    
    # Use only session state timestamps (deque)
    if hasattr(st.session_state, 'processing_timestamps') and st.session_state.processing_timestamps:
        # Iterate through deque to count recent timestamps
        # Deques are efficient for this kind of check
        recent_completions = [ts for ts in st.session_state.processing_timestamps if ts > one_minute_ago]
        message_count = len(recent_completions)
    
    # Detailed logging
    print(f"get_processing_throughput: current_time={current_time:.2f}, one_minute_ago={one_minute_ago:.2f}")
    print(f"get_processing_throughput: Found {len(st.session_state.processing_timestamps)} timestamps in session state deque.")
    print(f"get_processing_throughput: Calculated throughput={message_count} messages completed in the last 60 seconds")
    
    return message_count

def update_processing_timestamps():
    """Get timestamps from the queue and update session state, pruning old ones."""
    # Prune timestamps older than ~65 seconds to keep the deque size managed
    current_time = time.time()
    cutoff = current_time - 65  
    
    while st.session_state.processing_timestamps and st.session_state.processing_timestamps[0] < cutoff:
        st.session_state.processing_timestamps.popleft()
    
    print(f"update_processing_timestamps: Updated deque size: {len(st.session_state.processing_timestamps)}")

def main():
    """Main function to run the Streamlit app."""
    global kafka_consumer, kafka_producer
    
    # Initialize session state variables and start threads if they don't exist
    if 'initialized' not in st.session_state:
        st.session_state.initialized = True
        st.session_state.last_update_time = time.time()
        
        # Initialize Kafka consumer and producer
        kafka_consumer = KafkaConsumer(
            bootstrap_servers=os.getenv('KAFKA_BOOTSTRAP_SERVERS'),
            input_topic=os.getenv('KAFKA_INPUT_TOPIC'),
            group_id=os.getenv('KAFKA_GROUP_ID'),
            message_queue=message_queue
        )
        
        kafka_producer = KafkaProducer(
            bootstrap_servers=os.getenv('KAFKA_BOOTSTRAP_SERVERS'),
            output_topic=os.getenv('KAFKA_OUTPUT_TOPIC')
        )
        
        # Initialize the producer
        kafka_producer.initialize()
        
        # Start consumer thread
        kafka_consumer.start()
        
        # Start processor thread
        processor_thread = threading.Thread(target=process_messages_thread, daemon=True)
        processor_thread.start()
    else:
        # Only update the last_update_time if already initialized
        if 'last_update_time' not in st.session_state:
            st.session_state.last_update_time = time.time()
    
    # Force a session state refresh
    if st.sidebar.button("Force Refresh"):
        st.rerun()
        
    # Add a timestamp of last update
    current_time = time.time()
    seconds_since_update = current_time - st.session_state.last_update_time
    st.sidebar.text(f"Last update: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ({seconds_since_update:.1f}s ago)")
    st.session_state.last_update_time = current_time

    # Sync thread data to session state (for messages, latency, sentiment)
    sync_thread_data_to_session_state()

    # Update processing timestamps from queue into session state
    update_processing_timestamps()

    # Display number of messages for debugging
    st.sidebar.text(f"Messages in queue: {message_queue.qsize()}")
    
    # Dashboard view
    with st.container():
        st.title("Real-time Kafka Sentiment Analysis Dashboard")
        st.subheader("Real-time Metrics")
        data = load_data_from_warehouse()
        message_count = len(data['processed_messages']) if data['processed_messages'] else 0
        st.write(f"Calculating metrics from {message_count} processed messages")
        display_metrics()
    
    # Add a section to display recent messages
    with st.container():
        st.subheader("Recent Messages")
        
        # Get data from warehouse
        data = load_data_from_warehouse()
        messages = data['processed_messages']
        
        if not messages:
            st.info("No messages processed yet.")
        else:
            # Display most recent messages first (up to 10)
            for msg in list(reversed(messages))[:10]:
                sentiment_color = "#2ECC71" if msg.get('sentiment_score', 0) > 0.3 else "#E74C3C" if msg.get('sentiment_score', 0) < -0.3 else "#F5B041"
                
                # Format the expander title properly
                sentiment_score = msg.get('sentiment_score')
                timestamp = msg.get('processed_timestamp', 'Unknown time')
                
                if sentiment_score is not None and isinstance(sentiment_score, (int, float)):
                    expander_title = f"Message at {timestamp} - Sentiment: {sentiment_score:.2f}"
                else:
                    expander_title = f"Message at {timestamp} - Sentiment: {msg.get('sentiment_score', 'N/A')}"
                
                with st.expander(expander_title, expanded=False):
                    cols = st.columns([3, 1])
                    with cols[0]:
                        st.markdown(f"**Text:** {msg.get('original_text', 'N/A')}")
                    with cols[1]:
                        # Format correctly for numeric values
                        latency = msg.get('processing_time_ms')
                        if latency is not None and isinstance(latency, (int, float)):
                            st.markdown(f"**Processing Time:** {latency:.2f} ms")
                        else:
                            st.markdown(f"**Processing Time:** {msg.get('processing_time_ms', 'N/A')} ms")
                        
                        # Format sentiment score properly for display
                        if sentiment_score is not None and isinstance(sentiment_score, (int, float)):
                            st.markdown(f"<span style='color:{sentiment_color}'>**Sentiment Score:** {sentiment_score:.2f}</span>", unsafe_allow_html=True)
                        else:
                            st.markdown(f"<span style='color:{sentiment_color}'>**Sentiment Score:** {msg.get('sentiment_score', 'N/A')}</span>", unsafe_allow_html=True)
    
    # Recent Messages Table
    st.subheader("All Processed Messages")
    data = load_data_from_warehouse()
    messages = data['processed_messages']
    
    if messages:
        st.text(f"Displaying {len(messages)} processed messages:")
        df = pd.DataFrame(messages)
        # Format the dataframe for display
        columns_to_display = ['message_id', 'original_text', 'sentiment_label', 'sentiment_score', 'processing_time_ms']
        display_columns = [col for col in columns_to_display if col in df.columns]
        
        if display_columns:
            display_df = df[display_columns].copy()
            display_df = display_df.rename(columns={
                'message_id': 'ID',
                'original_text': 'Text',
                'sentiment_label': 'Sentiment',
                'sentiment_score': 'Score',
                'processing_time_ms': 'Processing Time (ms)'
            })
            st.dataframe(display_df, height=400, use_container_width=True)
    else:
        st.info("No messages processed yet.")
                            
    # Auto-refresh using Streamlit's native functionality
    if 'refresh_counter' not in st.session_state:
        st.session_state.refresh_counter = 0
        st.session_state.last_refresh = time.time()
    
    # Check if it's time to refresh (every 1 second)
    current_time = time.time()
    if current_time - st.session_state.last_refresh > 1:
        st.session_state.refresh_counter += 1
        st.session_state.last_refresh = current_time
        st.rerun()
        
    # Show refresh status
    st.text(f"Dashboard refreshes automatically every second. Last refresh: {datetime.datetime.fromtimestamp(st.session_state.last_refresh).strftime('%H:%M:%S')}")

# Add shutdown handler
def shutdown():
    """Ensure resources are properly closed when the app is interrupted"""
    global kafka_consumer, kafka_producer
    print("Shutting down Kafka application...")
    
    if kafka_producer:
        kafka_producer.shutdown()
    
    if kafka_consumer:
        kafka_consumer.shutdown()

# Register shutdown handler
import atexit
atexit.register(shutdown)

if __name__ == "__main__":
    main()
