# IMMEDIATE DEBUG - This should execute even if imports fail
import sys
print("DEBUG: Lambda starting - initial print statement")
sys.stdout.flush()

import logging
import os
import yaml
import json
import uuid
import random
import time
from datetime import datetime
from confluent_kafka import Producer, KafkaError, Consumer
import boto3
from typing import Dict, Optional
import base64

print("DEBUG: All imports successful")
sys.stdout.flush()

# Configure logging with more detail
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("customer-review-generator")
print("DEBUG: Logging configured")
sys.stdout.flush()

def load_config_from_secret(secret_name: str) -> Dict:
    """Load configuration from a secret in AWS Secrets Manager."""
    logger.info(f"Attempting to load config from secret: {secret_name}")
    try:
        client = boto3.client('secretsmanager')
        response = client.get_secret_value(SecretId=secret_name)
        secret_payload = response['SecretString']
        logger.info(f"Successfully loaded config from secret")
        return yaml.safe_load(secret_payload)
    except Exception as e:
        logger.critical(f"Failed to fetch configuration from Secrets Manager: {e}")
        raise

class BedrockClient:
    """A client for interacting with AWS Bedrock models."""

    def __init__(
        self,
        model_id: str = "us.anthropic.claude-3-5-sonnet-20241022-v2:0",  # Use inference profile for Claude 3.5 Sonnet v2
        region: str = "us-east-1",
        role_arn: str = None
    ):
        logger.info(f"Initializing BedrockClient with model: {model_id}, region: {region}")
        self.model_id = model_id
        self.region = region
        
        # If a role is provided, assume it for Bedrock access
        if role_arn:
            logger.info(f"Assuming role for Bedrock access: {role_arn}")
            try:
                sts_client = boto3.client('sts')
                assumed_role = sts_client.assume_role(
                    RoleArn=role_arn,
                    RoleSessionName="BedrockInferenceSession"
                )
                credentials = assumed_role['Credentials']
                logger.info(f"Successfully assumed role")
                
                self.bedrock_runtime = boto3.client(
                    service_name='bedrock-runtime',
                    region_name=region,
                    aws_access_key_id=credentials['AccessKeyId'],
                    aws_secret_access_key=credentials['SecretAccessKey'],
                    aws_session_token=credentials['SessionToken']
                )
            except Exception as e:
                logger.error(f"Failed to assume role: {e}")
                raise
        else:
            logger.info(f"Creating Bedrock client without role assumption")
            self.bedrock_runtime = boto3.client(
                service_name='bedrock-runtime',
                region_name=region
            )
        
        # Check model type for formatting
        self.is_claude = "anthropic" in self.model_id.lower()
        self.is_titan = "titan" in self.model_id.lower()
        self.is_nova = "nova" in self.model_id.lower()
        
        logger.info(f"Detected model type: Claude={self.is_claude}, Titan={self.is_titan}, Nova={self.is_nova}")
        logger.info(f"BedrockClient initialization complete")

    def _generate_dynamic_config(self) -> Dict:
        config = {
            "temperature": random.uniform(0.7, 0.99),
            "top_p": random.uniform(0.5, 1.0),
            "top_k": random.randint(20, 40),
            "max_tokens": random.randint(256, 768),
        }
        logger.debug(f"Generated dynamic config: {config}")
        return config

    def generate_content(
        self,
        prompt: str,
        custom_generation_config: Optional[Dict] = None,
    ) -> Dict:
        try:
            logger.info(f"Generating content with model: {self.model_id}")
            logger.debug(f"Prompt length: {len(prompt)} characters")
            
            generation_config = custom_generation_config or self._generate_dynamic_config()
            logger.info(f"Using generation config: temperature={generation_config['temperature']:.2f}, max_tokens={generation_config['max_tokens']}")
            
            # Format request based on model type
            if self.is_claude:
                logger.info("Using Claude API format")
                # Claude API format
                request_body = {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": generation_config["max_tokens"],
                    "temperature": generation_config["temperature"],
                    "top_p": generation_config["top_p"],
                    "top_k": generation_config.get("top_k", 40),
                    "messages": [
                        {"role": "user", "content": [{"type": "text", "text": prompt}]}
                    ]
                }
            elif self.is_nova:
                logger.info("Using Nova Pro API format")
                # Nova Pro specific format - exact format from error message
                request_body = {
                    "inferenceConfig": {
                        "max_new_tokens": generation_config["max_tokens"],
                        "temperature": generation_config["temperature"],
                        "top_p": generation_config["top_p"]
                    },
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "text": prompt
                                }
                            ]
                        }
                    ]
                }
            else:
                logger.info("Using generic ChatML format")
                # Generic ChatML format for other models (Titan, etc.)
                request_body = {
                    "inputText": prompt,
                    "textGenerationConfig": {
                        "maxTokenCount": generation_config["max_tokens"],
                        "temperature": generation_config["temperature"],
                        "topP": generation_config["top_p"]
                    }
                }
            
            logger.info(f"Request format: {json.dumps(request_body)[:200]}... (truncated)")
            
            logger.info(f"Invoking Bedrock model")
            start_time = time.time()
            response = self.bedrock_runtime.invoke_model(
                modelId=self.model_id,
                body=json.dumps(request_body)
            )
            elapsed_time = time.time() - start_time
            logger.info(f"Bedrock API call completed in {elapsed_time:.2f} seconds")
            
            response_body = json.loads(response.get('body').read())
            logger.info(f"Response format: {json.dumps(response_body)[:200]}... (truncated)")
            
            # Parse response based on model type
            result_text = ""
            if self.is_claude:
                logger.info("Parsing Claude response format")
                # Claude response format
                result_text = response_body.get('content')[0].get('text', '')
            elif self.is_nova:
                logger.info("Parsing Nova Pro response format")
                # Nova Pro response format - handling the nested structure
                try:
                    # Check if this is a string that needs to be parsed as JSON (happens sometimes)
                    if isinstance(response_body, str) or "output" not in response_body:
                        try:
                            # Try to parse it as JSON if it's a string
                            parsed_body = json.loads(response_body) if isinstance(response_body, str) else response_body
                            if isinstance(parsed_body, dict) and "output" in parsed_body:
                                response_body = parsed_body
                        except Exception as e:
                            logger.warning(f"Failed to parse response body as JSON: {e}")
                    
                    # Now try to extract from the proper structure
                    if "output" in response_body:
                        if "message" in response_body["output"]:
                            if "content" in response_body["output"]["message"]:
                                content = response_body["output"]["message"]["content"]
                                if isinstance(content, list) and len(content) > 0:
                                    if "text" in content[0]:
                                        result_text = content[0]["text"]
                                        logger.info("Successfully extracted text from Nova response")
                    
                    # If we still don't have text, try other formats
                    if not result_text:
                        result_text = response_body.get("output", {}).get("text", "")
                        if result_text:
                            logger.info("Extracted text from output.text fallback")
                except Exception as e:
                    logger.warning(f"Error parsing Nova response: {e}")
                    # Fall back to the full response as a string as a last resort
                    result_text = str(response_body)
                    logger.warning("Using full response string as fallback")
            else:
                logger.info("Parsing generic model response format")
                # Try different response formats for other models
                if "results" in response_body and len(response_body["results"]) > 0:
                    result_text = response_body["results"][0].get("outputText", "")
                    logger.info("Extracted text from results[0].outputText")
                elif "output" in response_body:
                    result_text = response_body["output"]
                    logger.info("Extracted text from output field")
                elif "completion" in response_body:
                    result_text = response_body["completion"]
                    logger.info("Extracted text from completion field")
                else:
                    # Last resort, try to convert the whole response to a string
                    result_text = str(response_body)
                    logger.warning("Using full response string as fallback")
            
            logger.info(f"Generated text length: {len(result_text)} characters")
            
            return {
                "texts": [result_text],
                "used_config": generation_config,
                "finish_reason": response_body.get("stopReason", response_body.get("stop_reason", "")),
                "safety_ratings": []
            }
        except Exception as e:
            logger.exception(f"Error generating content with Bedrock: {e}")
            raise

def retry_with_backoff(func, max_retries=3, initial_delay=1, backoff_factor=2):
    delay = initial_delay
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            logger.warning(f"Retry {attempt + 1}/{max_retries} failed: {e}")
            time.sleep(delay)
            delay *= backoff_factor
    logger.error(f"Operation failed after {max_retries} retries")
    raise

def generate_persona() -> Dict:
    """
    Generate a random persona based on age, profession, and cultural background.
    
    Returns:
        A dictionary containing the persona's details.
    """
    ages = range(18, 101)
    professions = [
        # Education
        "Teacher", "Professor", "School Principal", "Tutor", "Education Consultant", "School Counselor",
        
        # Technology
        "Software Developer", "Data Scientist", "Cybersecurity Analyst", "IT Support Specialist", 
        "UX Designer", "Cloud Architect", "Game Developer", "AI Researcher",
        
        # Healthcare
        "Nurse", "Doctor", "Dentist", "Paramedic", "Physical Therapist", "Pharmacist", 
        "Veterinarian", "Nutritionist", "Mental Health Counselor", "Midwife",
        
        # Trades & Blue-collar
        "Carpenter", "Electrician", "Plumber", "Auto Mechanic", "HVAC Technician", "Welder",
        "Construction Worker", "Landscaper", "Factory Worker", "Machinist",
        
        # Hospitality & Service
        "Chef", "Barista", "Server", "Hotel Manager", "Flight Attendant", "Bartender",
        "Restaurant Manager", "Housekeeper", "Caregiver", "Hairstylist",
        
        # Creative & Arts
        "Artist", "Actor", "Writer", "Musician", "Photographer", "Graphic Designer", 
        "Fashion Designer", "Interior Designer", "Animator", "Film Director",
        
        # Business & Finance
        "Accountant", "Financial Analyst", "Marketing Manager", "HR Manager", "Entrepreneur",
        "Salesperson", "Real Estate Agent", "Insurance Agent", "Business Consultant", "Investment Banker",
        
        # Science & Research
        "Scientist", "Researcher", "Lab Technician", "Biologist", "Chemist", "Astronomer",
        "Environmental Scientist", "Marine Biologist", "Geologist", "Archaeologist",
        
        # Legal & Public Service
        "Lawyer", "Police Officer", "Firefighter", "Social Worker", "Paralegal", "Judge", 
        "Government Employee", "Military Personnel", "Diplomat", "Nonprofit Worker", 
        
        # Transportation
        "Pilot", "Truck Driver", "Bus Driver", "Taxi Driver", "Ship Captain", "Train Engineer",
        "Delivery Driver", "Courier", "Air Traffic Controller", "Transportation Planner",
        
        # Agriculture & Natural Resources
        "Farmer", "Rancher", "Fisher", "Forester", "Agricultural Scientist", "Wildlife Biologist",
        "Park Ranger", "Gardener", "Florist", "Beekeeper",
        
        # Media & Communications
        "Journalist", "Translator", "Public Relations Specialist", "Social Media Manager",
        "Content Creator", "Podcaster", "TV Producer", "News Anchor", "Technical Writer", "Editor",
        
        # Specialized & Emerging
        "Drone Operator", "Sustainability Consultant", "Blockchain Developer", "E-sports Player",
        "Robotics Engineer", "Virtual Reality Designer", "Genetic Counselor", "Renewable Energy Technician",
        "Biomedical Engineer", "Telemedicine Physician",
        
        # Other Diverse Roles
        "Librarian", "Athlete", "Personal Trainer", "Tailor", "Baker", "Jeweler",
        "Tour Guide", "Yoga Instructor", "Massage Therapist", "Community Organizer"
    ]
    cultural_backgrounds = [
        "American", "Chinese", "Indian", "French", "Mexican", "Italian", "Japanese",
        "Brazilian", "German", "Nigerian", "Russian", "South African", "Korean",
        "Australian", "British", "Egyptian", "Canadian", "Spanish", "Turkish",
        "Indigenous", "Middle Eastern", "Caribbean", "Southeast Asian", "Scandinavian",
        "Pacific Islander", "Eastern European", "Latin American", "Sub-Saharan African"
    ]

    persona = {
        "age": random.choice(ages),
        "profession": random.choice(professions),
        "cultural_background": random.choice(cultural_backgrounds),
    }
    return persona

def adapt_prompt_with_persona(scenario: str, sentiment: str, mood: str, persona: Dict) -> str:
    """
    Adapt a review scenario into a detailed prompt with persona details.
    
    Args:
        scenario (str): The basic scenario description
        sentiment (str): The sentiment (positive, negative, neutral)
        mood (str): The specific mood/emotion
        persona (Dict): Details about the reviewer's persona
        
    Returns:
        str: A detailed prompt for the LLM
    """
    logger.info(f"Creating prompt with scenario: '{scenario}', sentiment: {sentiment}, mood: {mood}")
    
    age = persona.get("age", "35")
    profession = persona.get("profession", "professional")
    cultural_background = persona.get("cultural_background", "German")
    
    logger.info(f"Using persona: age={age}, profession={profession}, cultural_background={cultural_background}")
    
    prompt = f"""You are a {age}-year-old {profession} with a {cultural_background} cultural background.
Write a car insurance customer review expressing a {sentiment} {mood} experience about: "{scenario}".

Your review should be:
1. Written in first person
2. Natural-sounding, like a real customer review
3. 3-6 sentences in length
4. Reflect the {sentiment} sentiment and {mood} emotional tone
5. Include realistic details
6. Mention specific aspects of car insurance service
7. Relate to your persona as a {profession} with {cultural_background} background, but subtly

Write ONLY the review text, with no additional context, labels, or formatting."""

    logger.debug(f"Generated prompt: {prompt}")
    return prompt

def fetch_secret(secret_name: str) -> str:
    """Fetch a secret value from AWS Secrets Manager."""
    logger.info(f"Fetching secret from AWS Secrets Manager: {secret_name}")
    try:
        client = boto3.client('secretsmanager')
        response = client.get_secret_value(SecretId=secret_name)
        secret_string = response['SecretString']
        logger.info(f"Successfully fetched secret: {secret_name}")
        return secret_string
    except Exception as e:
        logger.error(f"Error fetching secret {secret_name}: {e}")
        raise

def lambda_handler(event, context):
    # DEBUG: Print full event immediately with safeguards
    print("========== DEBUG EVENT RECEIVED ==========")
    try:
        print(json.dumps(event, indent=2, default=str))
    except Exception as e:
        print(f"Failed to JSON serialize full event: {e}")
        # Print event in raw format as fallback
        print(f"Raw event: {event}")
    print("=========================================")
    sys.stdout.flush()
    
    logger.info("=== Initializing customer-review-creator Lambda function ===")
    
    # Log the event (for debugging)
    logger.debug(f"Received event: {json.dumps(event)[:1000]}...")
    
    # Fetch configurations from environment variables
    output_kafka_topic = os.getenv("KAFKA_TOPIC_NAME")
    bootstrap_server = os.getenv("KAFKA_BOOTSTRAP_SERVER")
    secret_name = os.getenv("SECRET_NAME")
    kafka_api_key_id = os.getenv("KAFKA_API_KEY_ID")
    seconds_between_reviews = int(os.getenv("SECONDS_BETWEEN_REVIEWS", "1"))
    review_probability = float(os.getenv("REVIEW_PROBABILITY", "0.25"))  # Default to 25% chance of review
    
    logger.info(f"Configuration loaded:")
    logger.info(f"- Output Kafka Topic: {output_kafka_topic}")
    logger.info(f"- Kafka Bootstrap Server: {bootstrap_server}")
    logger.info(f"- Secret Name: {secret_name}")
    logger.info(f"- Review Probability: {review_probability}")
    
    # Get model configuration - use inference profile for Claude 3.5 Sonnet v2
    model_id = os.getenv("MODEL_ID", "us.anthropic.claude-3-5-sonnet-20241022-v2:0")
    logger.info(f"Using model: {model_id}")
    
    # Get the role ARN for Bedrock inference if provided
    bedrock_role_arn = os.getenv("BEDROCK_ROLE_ARN")
    if bedrock_role_arn:
        logger.info(f"Using role for Bedrock inference: {bedrock_role_arn}")

    # Fetch Kafka API key secret from Secrets Manager
    try:
        logger.info(f"Fetching Kafka API key secret from Secrets Manager: {secret_name}")
        kafka_api_key_secret = fetch_secret(secret_name)
        logger.info(f"Successfully fetched Kafka API key secret")
    except Exception as e:
        logger.error(f"Failed to fetch Kafka API key secret: {e}")
        raise

    kafka_config = {
        'bootstrap.servers': bootstrap_server,
        'security.protocol': "SASL_SSL",
        'sasl.mechanisms': "PLAIN",
        'sasl.username': kafka_api_key_id,
        'sasl.password': kafka_api_key_secret
    }

    # Create a producer for sending reviews
    try:
        logger.info(f"Initializing Kafka producer for topic: {output_kafka_topic}")
        producer = Producer(kafka_config)
        logger.info(f"Kafka producer successfully initialized")
    except Exception as e:
        logger.error(f"Failed to initialize Kafka producer: {e}")
        raise
    
    # Initialize Bedrock client with the specified model and role if available
    try:
        logger.info(f"Initializing Bedrock client with model: {model_id}")
        bedrock_client = BedrockClient(model_id=model_id, role_arn=bedrock_role_arn)
        logger.info(f"Bedrock client successfully initialized")
    except Exception as e:
        logger.error(f"Failed to initialize Bedrock client: {e}")
        raise

    # Load scenarios from CSV files
    def load_scenarios_from_csv(file_path):
        scenarios = []
        try:
            with open(file_path, 'r') as file:
                # Skip header line
                next(file)
                for line in file:
                    scenario = line.strip()
                    if scenario:  # Skip empty lines
                        scenarios.append(scenario)
            logger.info(f"Loaded {len(scenarios)} scenarios from {file_path}")
            return scenarios
        except Exception as e:
            logger.error(f"Error loading scenarios from {file_path}: {e}")
            return []

    # Get the directory containing the current file
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Load scenarios from CSV files
    logger.info(f"Loading scenarios from CSV files")
    positive_scenarios = load_scenarios_from_csv(os.path.join(current_dir, "positive_scenarios.csv"))
    negative_scenarios = load_scenarios_from_csv(os.path.join(current_dir, "negative_scenarios.csv"))
    neutral_scenarios = load_scenarios_from_csv(os.path.join(current_dir, "neutral_scenarios.csv"))
    
    # If any file failed to load, use default minimal lists
    if not positive_scenarios:
        positive_scenarios = ["Excellent customer service experience", "Quick claims processing"]
    if not negative_scenarios:
        negative_scenarios = ["Poor customer service experience", "Delayed claims processing"]
    if not neutral_scenarios:
        neutral_scenarios = ["Average customer service experience", "Standard claims processing"]

    # Expanded moods associated with sentiments
    positive_moods = ["satisfied", "happy", "impressed", "grateful", "relieved", "delighted", "pleased", "content", "appreciative", "optimistic"]
    negative_moods = ["frustrated", "disappointed", "annoyed", "angry", "concerned", "upset", "dissatisfied", "irritated", "discouraged", "skeptical"]
    neutral_moods = ["neutral", "indifferent", "objective", "matter-of-fact", "unbiased", "impartial", "balanced", "reserved", "moderate", "composed"]

    # Process the incoming records from the Lambda Sink Connector
    processed_records = 0
    review_count = 0
    
    try:
        # Lambda Sink Connector format:
        # event = {
        #    "records": [
        #        {
        #            "key": "base64-encoded-key",
        #            "value": "base64-encoded-value",
        #            "topic": "topic-name",
        #            "partition": 0,
        #            "offset": 1234
        #        },
        #        ...
        #    ]
        # }
        
        if "records" not in event:
            logger.warning("No records found in event. Expected format from Lambda Sink Connector not found.")
            return {"statusCode": 200, "body": json.dumps({"message": "No records to process"})}
        
        records = event.get("records", [])
        logger.info(f"Received {len(records)} records from Lambda Sink Connector")
        
        for record in records:
            processed_records += 1
            
            try:
                # Extract and decode the policy data from the record
                encoded_value = record.get("value", "")
                if not encoded_value:
                    logger.warning(f"Record {processed_records} has no value, skipping")
                    continue
                
                # Decode base64 value
                try:
                    decoded_value = base64.b64decode(encoded_value).decode('utf-8')
                    policy_data = json.loads(decoded_value)
                    logger.info(f"Successfully decoded policy data from record {processed_records}")
                except Exception as e:
                    logger.error(f"Failed to decode record {processed_records}: {e}")
                    continue
                
                # Randomly decide if we should generate a review for this policy
                if random.random() < review_probability:
                    logger.info(f"Selected policy {processed_records} for review generation (probability: {review_probability})")
                    
                    # Extract persona information from the policy
                    profession = policy_data.get('Profession', 'Professional')
                    background = policy_data.get('CulturalBackground', 'German')
                    logger.info(f"Extracted persona: Profession={profession}, Background={background}")
                    
                    persona = {
                        "age": random.randint(25, 70),  # Random age since not in policy data
                        "profession": profession,
                        "cultural_background": background
                    }
                    
                    # Randomly select sentiment (positive, negative, or neutral)
                    sentiment = random.choice(["positive", "negative", "neutral"])
                    logger.info(f"Selected sentiment: {sentiment}")
                    
                    # Choose scenarios and moods based on sentiment
                    if sentiment == "positive":
                        scenario = random.choice(positive_scenarios)
                        mood = random.choice(positive_moods)
                    elif sentiment == "negative":
                        scenario = random.choice(negative_scenarios)
                        mood = random.choice(negative_moods)
                    else:
                        scenario = random.choice(neutral_scenarios)
                        mood = random.choice(neutral_moods)
                    
                    logger.info(f"Selected scenario: '{scenario}' with mood: '{mood}'")
                    
                    # Generate a detailed prompt with persona
                    prompt = adapt_prompt_with_persona(scenario, sentiment, mood, persona)
                    logger.info(f"Generated prompt for Bedrock (length: {len(prompt)} chars)")
                    
                    # Generate review content using Bedrock
                    logger.info(f"Calling Bedrock to generate review content...")
                    generation_result = bedrock_client.generate_content(prompt)
                    logger.info(f"Successfully received response from Bedrock")
                    
                    # Extract the first generated review text
                    review_text = generation_result["texts"][0] if generation_result["texts"] else ""
                    review_length = len(review_text)
                    logger.info(f"Generated review text (length: {review_length} chars)")
                    
                    # Clean up review text
                    review_text = review_text.strip()
                    
                    # If it still looks like JSON or has excessive quotes, clean it
                    if review_text.startswith('{') and review_text.endswith('}'):
                        logger.info(f"Cleaning up JSON-like review text")
                        try:
                            # Try to parse as JSON and extract text
                            parsed = json.loads(review_text)
                            if isinstance(parsed, dict):
                                # Try to navigate nested content
                                if "output" in parsed and "message" in parsed["output"] and "content" in parsed["output"]["message"]:
                                    content = parsed["output"]["message"]["content"]
                                    if isinstance(content, list) and len(content) > 0 and "text" in content[0]:
                                        review_text = content[0]["text"]
                                        logger.info(f"Extracted text from JSON response")
                        except Exception as e:
                            logger.warning(f"Failed to parse JSON response: {e}")
                    
                    # Remove any excessive quotes
                    if review_text.startswith('"') and review_text.endswith('"'):
                        review_text = review_text[1:-1]
                        
                    # Create a review object with policy reference
                    review_id = str(uuid.uuid4())
                    review_data = {
                        "id": review_id,
                        "text": review_text,
                        "sentiment": sentiment,
                        "scenario": scenario,
                        "timestamp": datetime.utcnow().isoformat(),
                        "source": "policy_consumer",
                        "policy_reference": policy_data.get('UserID', ''),
                        "persona": {
                            "age": persona["age"],
                            "profession": persona["profession"],
                            "cultural_background": persona["cultural_background"]
                        }
                    }
                    
                    # Produce to Kafka
                    logger.info(f"Producing review {review_id} to Kafka topic: {output_kafka_topic}")
                    producer.produce(
                        output_kafka_topic,
                        key=review_id,
                        value=json.dumps(review_data)
                    )
                    producer.flush()
                    
                    logger.info(f"Review {review_id} ({sentiment}) successfully produced to Kafka")
                    review_count += 1
                    
                    # Add a small delay between reviews to avoid overloading the system
                    if seconds_between_reviews > 0:
                        logger.info(f"Sleeping for {seconds_between_reviews} seconds before processing next review")
                        time.sleep(seconds_between_reviews)
                else:
                    logger.info(f"Policy #{processed_records} not selected for review generation ({(1-review_probability)*100:.0f}% probability)")
            except Exception as e:
                logger.error(f"Error processing record {processed_records}: {str(e)}", exc_info=True)
    
    except Exception as e:
        logger.error(f"Error processing event: {str(e)}", exc_info=True)
        raise
    
    # Return a summary of the operation
    summary = {
        "statusCode": 200,
        "body": json.dumps({
            "message": f"Processed {processed_records} policies and generated {review_count} reviews",
            "policies_processed": processed_records,
            "reviews_produced": review_count
        })
    }
    
    logger.info(f"=== Lambda execution complete: {summary['body']} ===")
    return summary 