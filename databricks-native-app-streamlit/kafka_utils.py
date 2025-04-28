import os
import json
import threading
import queue
import time
from typing import Dict, Any, Callable, Optional
from confluent_kafka import Consumer, Producer, KafkaError
import traceback

class KafkaConfig:
    """Base class for Kafka configuration."""
    
    def __init__(self, bootstrap_servers: str):
        """Initialize with bootstrap servers."""
        self.bootstrap_servers = bootstrap_servers
    
    def get_base_config(self) -> Dict[str, Any]:
        """Get basic Kafka configuration with security settings."""
        config = {
            'bootstrap.servers': self.bootstrap_servers,
        }
        
        # Add security configuration if credentials are provided
        if os.getenv('KAFKA_SECURITY_PROTOCOL'):
            config.update({
                'security.protocol': os.getenv('KAFKA_SECURITY_PROTOCOL'),
                'sasl.mechanism': os.getenv('KAFKA_SASL_MECHANISM', 'PLAIN'),
                'sasl.username': os.getenv('KAFKA_SASL_USERNAME'),
                'sasl.password': os.getenv('KAFKA_SASL_PASSWORD')
            })
        
        return config

class KafkaProducer(KafkaConfig):
    """Kafka producer for sending messages to topics."""
    
    def __init__(self, bootstrap_servers: str, output_topic: str):
        """Initialize the Kafka producer."""
        super().__init__(bootstrap_servers)
        self.output_topic = output_topic
        self.producer = None
    
    def delivery_callback(self, err, msg):
        """Callback for Kafka delivery reports."""
        if err:
            print(f'Message delivery failed: {err}')
        else:
            print(f'Message delivered to {msg.topic()} [{msg.partition()}] at offset {msg.offset()}')
    
    def initialize(self):
        """Initialize the Kafka producer."""
        if self.producer is None:
            producer_conf = self.get_base_config()
            
            # Add error callback
            def error_cb(err):
                print(f"Kafka producer error: {err}")
            
            producer_conf['error_cb'] = error_cb
            
            # Add additional configs for better reliability
            producer_conf.update({
                'acks': 'all',                 # Wait for all replicas
                'enable.idempotence': True,    # Prevent duplicates
                'max.in.flight.requests.per.connection': 5,  # Ensure ordering
                'retries': 5,                  # Retry on failures
                'retry.backoff.ms': 500        # Backoff time between retries
            })
            
            self.producer = Producer(producer_conf)
            print("Initialized Kafka producer")
        
        return self.producer
    
    def send_message(self, message: Dict[str, Any], topic: Optional[str] = None):
        """Send message to a Kafka topic."""
        # Get or initialize the producer
        if self.producer is None:
            self.initialize()
        
        # Use specified topic or default output topic
        output_topic = topic or self.output_topic
        print(f"Sending message to output topic: {output_topic}")
        
        try:
            # Use message ID as the key for better partitioning
            key = message.get('message_id', str(time.time())).encode('utf-8')
            payload = json.dumps(message).encode('utf-8')
            
            self.producer.produce(
                output_topic,
                value=payload,
                key=key,
                callback=self.delivery_callback
            )
            # Only poll, don't flush here to avoid blocking
            self.producer.poll(0)  # Trigger any available delivery callbacks
        except Exception as e:
            print(f"Error sending to Kafka: {e}")
            print(traceback.format_exc())
    
    def flush(self, timeout=10):
        """Flush any pending messages in the producer."""
        if self.producer:
            try:
                print("Flushing Kafka producer...")
                self.producer.flush(timeout=timeout)
                print("Kafka producer flushed successfully")
            except Exception as e:
                print(f"Error flushing Kafka producer: {e}")
    
    def shutdown(self):
        """Shutdown the producer."""
        self.flush()
        print("Kafka producer shut down")

class KafkaConsumer(KafkaConfig):
    """Kafka consumer for receiving messages from topics."""
    
    def __init__(self, bootstrap_servers: str, input_topic: str, 
                 group_id: str, message_queue: queue.Queue):
        """Initialize the Kafka consumer."""
        super().__init__(bootstrap_servers)
        self.input_topic = input_topic
        self.group_id = group_id
        self.message_queue = message_queue
        self.running = True
        self._consumer_thread = None
    
    def get_consumer_config(self) -> Dict[str, Any]:
        """Get consumer configuration."""
        config = self.get_base_config()
        config.update({
            'group.id': self.group_id,
            'auto.offset.reset': 'earliest'
        })
        return config
    
    def start(self):
        """Start a background thread to consume messages from Kafka."""
        if self._consumer_thread is None or not self._consumer_thread.is_alive():
            self.running = True
            self._consumer_thread = threading.Thread(target=self._consume_messages, daemon=True)
            self._consumer_thread.start()
        return self._consumer_thread
    
    def _consume_messages(self):
        """Background thread to consume messages from Kafka."""
        # Configure the consumer with security settings
        consumer_conf = self.get_consumer_config()
        
        # Create consumer
        consumer = Consumer(consumer_conf)
        consumer.subscribe([self.input_topic])
        
        try:
            while self.running:
                msg = consumer.poll(1.0)
                
                if msg is None:
                    continue
                    
                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    else:
                        print(f"Consumer error: {msg.error()}")
                        break
                
                # Process the message
                try:
                    print(f"Received message from Kafka topic: {msg.topic()}")
                    value = json.loads(msg.value().decode('utf-8'))
                    value['receive_time'] = time.time()
                    self.message_queue.put(value)
                    print(f"Added message to queue, current size: {self.message_queue.qsize()}")
                except Exception as e:
                    print(f"Error processing message: {e}")
                    print(traceback.format_exc())
        finally:
            consumer.close()
            print("Kafka consumer closed")
    
    def shutdown(self):
        """Stop consuming messages."""
        self.running = False
        print("Kafka consumer shutdown initiated") 