import os
import json
import threading
import time
from typing import Dict, Any, Optional
from kafka import KafkaConsumer as KC, KafkaProducer as KP
import queue
import traceback

class KafkaConsumer:
    def __init__(self, bootstrap_servers: str, input_topic: str, group_id: str, message_queue: queue.Queue):
        self.bootstrap_servers = bootstrap_servers
        self.input_topic = input_topic
        self.group_id = group_id
        self.message_queue = message_queue
        self.running = True
        self.consumer = None
        self.consumer_thread = None
        
    def start(self):
        """Start the Kafka consumer in a background thread"""
        self.consumer_thread = threading.Thread(target=self._consume_messages, daemon=True)
        self.consumer_thread.start()
        print(f"Started Kafka consumer thread for topic {self.input_topic}")
        
    def _consume_messages(self):
        """Consume messages from Kafka and add to queue"""
        try:
            # Configure Kafka consumer
            sasl_config = {}
            if os.getenv('KAFKA_SASL_USERNAME') and os.getenv('KAFKA_SASL_PASSWORD'):
                sasl_config = {
                    'security_protocol': os.getenv('KAFKA_SECURITY_PROTOCOL', 'SASL_SSL'),
                    'sasl_mechanism': os.getenv('KAFKA_SASL_MECHANISM', 'PLAIN'),
                    'sasl_plain_username': os.getenv('KAFKA_SASL_USERNAME'),
                    'sasl_plain_password': os.getenv('KAFKA_SASL_PASSWORD')
                }
            
            # Create consumer
            self.consumer = KC(
                bootstrap_servers=self.bootstrap_servers,
                group_id=self.group_id,
                auto_offset_reset='latest',
                value_deserializer=lambda x: json.loads(x.decode('utf-8')),
                **sasl_config
            )
            
            # Subscribe to topic
            self.consumer.subscribe([self.input_topic])
            print(f"Subscribed to topic: {self.input_topic}")
            
            # Consume messages in a loop
            while self.running:
                # Poll for messages with a timeout
                records = self.consumer.poll(timeout_ms=1000)
                for tp, messages in records.items():
                    for message in messages:
                        try:
                            # Add message to queue
                            value = message.value
                            # Add timestamp for latency calculations
                            if isinstance(value, dict):
                                if 'create_time' not in value:
                                    value['create_time'] = time.time()
                            else:
                                value = {'text': str(value), 'create_time': time.time()}
                                
                            message_data = {
                                'id': f"{tp.topic}-{tp.partition}-{message.offset}",
                                'value': value,
                                'create_time': time.time()
                            }
                            
                            print(f"Received message: {message_data}")
                            self.message_queue.put(message_data)
                        except Exception as e:
                            print(f"Error processing message: {e}")
                            print(traceback.format_exc())
                            
        except Exception as e:
            print(f"Consumer thread error: {e}")
            print(traceback.format_exc())
        finally:
            if self.consumer:
                try:
                    self.consumer.close()
                    print("Kafka consumer closed")
                except:
                    pass
                
    def shutdown(self):
        """Gracefully shut down the consumer"""
        print("Shutting down Kafka consumer...")
        self.running = False
        if self.consumer_thread:
            self.consumer_thread.join(timeout=5)
        if self.consumer:
            try:
                self.consumer.close()
            except:
                pass
        print("Kafka consumer shutdown complete")


class KafkaProducer:
    def __init__(self, bootstrap_servers: str, output_topic: str):
        self.bootstrap_servers = bootstrap_servers
        self.output_topic = output_topic
        self.producer = None
    
    def initialize(self):
        """Initialize the Kafka producer"""
        try:
            # Configure Kafka producer
            sasl_config = {}
            if os.getenv('KAFKA_SASL_USERNAME') and os.getenv('KAFKA_SASL_PASSWORD'):
                sasl_config = {
                    'security_protocol': os.getenv('KAFKA_SECURITY_PROTOCOL', 'SASL_SSL'),
                    'sasl_mechanism': os.getenv('KAFKA_SASL_MECHANISM', 'PLAIN'),
                    'sasl_plain_username': os.getenv('KAFKA_SASL_USERNAME'),
                    'sasl_plain_password': os.getenv('KAFKA_SASL_PASSWORD')
                }
            
            # Create producer
            self.producer = KP(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                **sasl_config
            )
            print(f"Initialized Kafka producer for topic {self.output_topic}")
        except Exception as e:
            print(f"Error initializing Kafka producer: {e}")
            print(traceback.format_exc())
    
    def send_message(self, message: Dict[str, Any]):
        """Send a message to the Kafka topic"""
        if not self.producer:
            print("Producer not initialized, initializing now...")
            self.initialize()
            
        try:
            # Send message
            self.producer.send(self.output_topic, message)
            print(f"Sent message to topic {self.output_topic}: {message}")
        except Exception as e:
            print(f"Error sending message: {e}")
            print(traceback.format_exc())
    
    def flush(self, timeout=None):
        """Flush any pending messages"""
        if self.producer:
            try:
                self.producer.flush(timeout=timeout)
            except Exception as e:
                print(f"Error flushing producer: {e}")
                
    def shutdown(self):
        """Gracefully shut down the producer"""
        print("Shutting down Kafka producer...")
        if self.producer:
            try:
                self.producer.flush(timeout=5)
                self.producer.close(timeout=5)
            except:
                pass
        print("Kafka producer shutdown complete") 