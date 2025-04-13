import logging
import os
import yaml
import json
import uuid
import random
import time
from datetime import datetime
from confluent_kafka import Producer, KafkaError
import boto3
from typing import Dict, Optional

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("customer-review-generator")

def load_config_from_secret(secret_name: str) -> Dict:
    """Load configuration from a secret in AWS Secrets Manager."""
    try:
        client = boto3.client('secretsmanager')
        response = client.get_secret_value(SecretId=secret_name)
        secret_payload = response['SecretString']
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
        self.model_id = model_id
        self.region = region
        
        # If a role is provided, assume it for Bedrock access
        if role_arn:
            sts_client = boto3.client('sts')
            assumed_role = sts_client.assume_role(
                RoleArn=role_arn,
                RoleSessionName="BedrockInferenceSession"
            )
            credentials = assumed_role['Credentials']
            
            self.bedrock_runtime = boto3.client(
                service_name='bedrock-runtime',
                region_name=region,
                aws_access_key_id=credentials['AccessKeyId'],
                aws_secret_access_key=credentials['SecretAccessKey'],
                aws_session_token=credentials['SessionToken']
            )
        else:
            self.bedrock_runtime = boto3.client(
                service_name='bedrock-runtime',
                region_name=region
            )
        
        # Check model type for formatting
        self.is_claude = "anthropic" in self.model_id.lower()
        self.is_titan = "titan" in self.model_id.lower()
        self.is_nova = "nova" in self.model_id.lower()

    def _generate_dynamic_config(self) -> Dict:
        return {
            "temperature": random.uniform(0.7, 0.99),
            "top_p": random.uniform(0.5, 1.0),
            "top_k": random.randint(20, 40),
            "max_tokens": random.randint(256, 768),
        }

    def generate_content(
        self,
        prompt: str,
        custom_generation_config: Optional[Dict] = None,
    ) -> Dict:
        try:
            generation_config = custom_generation_config or self._generate_dynamic_config()
            
            # Format request based on model type
            if self.is_claude:
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
                # Generic ChatML format for other models (Titan, etc.)
                request_body = {
                    "inputText": prompt,
                    "textGenerationConfig": {
                        "maxTokenCount": generation_config["max_tokens"],
                        "temperature": generation_config["temperature"],
                        "topP": generation_config["top_p"]
                    }
                }
            
            logger.info(f"Using model: {self.model_id}")
            logger.info(f"Request format: {json.dumps(request_body)}")
            
            response = self.bedrock_runtime.invoke_model(
                modelId=self.model_id,
                body=json.dumps(request_body)
            )
            
            response_body = json.loads(response.get('body').read())
            logger.info(f"Response format: {json.dumps(response_body)}")
            
            # Parse response based on model type
            result_text = ""
            if self.is_claude:
                # Claude response format
                result_text = response_body.get('content')[0].get('text', '')
            elif self.is_nova:
                # Nova Pro response format - handling the nested structure
                try:
                    # Check if this is a string that needs to be parsed as JSON (happens sometimes)
                    if isinstance(response_body, str) or "output" not in response_body:
                        try:
                            # Try to parse it as JSON if it's a string
                            parsed_body = json.loads(response_body) if isinstance(response_body, str) else response_body
                            if isinstance(parsed_body, dict) and "output" in parsed_body:
                                response_body = parsed_body
                        except:
                            pass
                    
                    # Now try to extract from the proper structure
                    if "output" in response_body:
                        if "message" in response_body["output"]:
                            if "content" in response_body["output"]["message"]:
                                content = response_body["output"]["message"]["content"]
                                if isinstance(content, list) and len(content) > 0:
                                    if "text" in content[0]:
                                        result_text = content[0]["text"]
                    
                    # If we still don't have text, try other formats
                    if not result_text:
                        result_text = response_body.get("output", {}).get("text", "")
                except Exception as e:
                    logger.warning(f"Error parsing Nova response: {e}")
                    # Fall back to the full response as a string as a last resort
                    result_text = str(response_body)
            else:
                # Try different response formats for other models
                if "results" in response_body and len(response_body["results"]) > 0:
                    result_text = response_body["results"][0].get("outputText", "")
                elif "output" in response_body:
                    result_text = response_body["output"]
                elif "completion" in response_body:
                    result_text = response_body["completion"]
                else:
                    # Last resort, try to convert the whole response to a string
                    result_text = str(response_body)
            
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
        "Teacher", "Software Developer", "Nurse", "Chef", "Artist", "Engineer", "Lawyer",
        "Doctor", "Carpenter", "Actor", "Writer", "Farmer", "Musician", "Scientist",
        "Accountant", "Mechanic", "Police Officer", "Salesperson", "Designer", "Athlete",
        "Barista", "Pilot", "Librarian", "Photographer", "Social Worker", "Entrepreneur",
        "Journalist", "Electrician", "Dentist", "Translator"
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
    Adapt the prompt to include a persona's details and adjust the style accordingly.
    
    Args:
        scenario: The scenario for the review.
        sentiment: The sentiment of the review ("positive" or "negative").
        mood: The mood associated with the sentiment.
        persona: The persona to use for this review.
        
    Returns:
        A detailed prompt string including persona details.
    """
    persona_description = (
        f"{persona['age']}-year-old {persona['profession']} "
        f"with a {persona['cultural_background']} background"
    )

    # Adapt the tone and style based on persona
    tone_instructions = (
        "Use casual and youthful language with some slang." if persona["age"] < 30 else
        "Use professional and articulate language." if persona["age"] < 60 else
        "Use reflective and mature language, perhaps nostalgic."
    )

    prompt = f"""
        User input:
        Embody a persona of a {persona_description}. 
        Scenario: {scenario}
        Sentiment: {mood}
        Style: {tone_instructions}
        Create a vivid and creative review for an insurance company called Insurancia. 
        Include minor typos and varied writing styles to reflect the persona. 
        Do not repeat the persona details. Just use them as a basis for the review.
        Only provide the final review text. Do not include any other text.
        Length: 30-70 words.
        Answer:
    """
    return prompt

def fetch_secret(secret_name: str) -> str:
    """Fetch a secret value from AWS Secrets Manager."""
    client = boto3.client('secretsmanager')
    response = client.get_secret_value(SecretId=secret_name)
    return response['SecretString']

def lambda_handler(event, context):
    logger.info("Initializing the Lambda function")

    # Fetch configurations from environment variables
    kafka_topic_name = os.getenv("KAFKA_TOPIC_NAME")
    bootstrap_server = os.getenv("KAFKA_BOOTSTRAP_SERVER")
    secret_name = os.getenv("SECRET_NAME")
    kafka_api_key_id = os.getenv("KAFKA_API_KEY_ID")
    min_reviews_per_run = int(os.getenv("MIN_RECORDS_PER_RUN", "10"))
    max_reviews_per_run = int(os.getenv("MAX_RECORDS_PER_RUN", "20"))
    seconds_between_reviews = int(os.getenv("SECONDS_BETWEEN_REVIEWS"))
    
    # Get model configuration - use inference profile for Claude 3.5 Sonnet v2
    model_id = os.getenv("MODEL_ID", "us.anthropic.claude-3-5-sonnet-20241022-v2:0")
    logger.info(f"Using model: {model_id}")
    
    # Get the role ARN for Bedrock inference if provided
    bedrock_role_arn = os.getenv("BEDROCK_ROLE_ARN")
    if bedrock_role_arn:
        logger.info(f"Using role for Bedrock inference: {bedrock_role_arn}")

    # Fetch Kafka API key secret from Secrets Manager
    kafka_api_key_secret = fetch_secret(secret_name)

    kafka_config = {
        'bootstrap.servers': bootstrap_server,
        'security.protocol': "SASL_SSL",
        'sasl.mechanisms': "PLAIN",
        'sasl.username': kafka_api_key_id,
        'sasl.password': kafka_api_key_secret
    }

    # Create a producer instance
    producer = Producer(kafka_config)

    # Initialize Bedrock client with the specified model and role if available
    bedrock_client = BedrockClient(model_id=model_id, role_arn=bedrock_role_arn)

    # Define scenarios and sentiments with much more diversity
    positive_scenarios = [
        # Car insurance
        "Quick claims processing for car insurance",
        "Excellent roadside assistance after a breakdown",
        "Helpful support after a car accident",
        "Fair car insurance rate after a minor traffic violation",
        "Easy process for adding a teen driver to my policy",
        "Great discount for installing anti-theft devices",
        "Smooth experience transferring policy to a new vehicle",
        "Impressed with the accident forgiveness feature",
        "Fast approval for rental car coverage after accident",
        "Transparent explanation of my car insurance deductible",
        "Great customer support when filing a windshield damage claim",
        "Helpful agent who found me additional discounts",
        "Convenient mobile app for submitting accident photos",
        "Reasonable premium reduction after taking defensive driving course",
        "Responsive agent when I needed to make policy changes",
        "Impressive courtesy vehicle while my car was in repair",
        "Helpful support team for filing a hit-and-run claim",
        "Great coverage for personal items stolen from my car",
        "Appreciative of their fast towing service after breakdown",
        "Simple online process to add a new driver",
        
        # Business/Other insurance
        "Simple policy renewal process",
        "Affordable premiums for comprehensive coverage",
        "Smooth mobile app experience for policy management",
        "Excellent coverage for my small business",
        "Great cyber insurance options for my online store",
        "Pet insurance that covered emergency surgery costs",
        "Travel insurance that came through during trip cancellation",
        "Rental insurance that was quick to activate"
    ]
    
    negative_scenarios = [
        # Car insurance
        "Delay in claims processing for car insurance",
        "Inadequate roadside assistance when stranded",
        "Unhelpful support after a not-at-fault accident",
        "Unfair rate increase after a minor fender bender",
        "Complicated process to insure a modified vehicle",
        "Disappointing settlement amount for my totaled car",
        "Poor communication during accident claim process",
        "Frustrating experience trying to get a claim approved",
        "Excessive premium increase after my first small claim",
        "Denied coverage for damages clearly within policy scope",
        "Difficult time reaching an agent after business hours",
        "Poor customer service when disputing a claim decision",
        "Unhelpful roadside assistance that left me stranded",
        "Confusing policy terms about collision coverage",
        "Excessive wait time for an adjuster after an accident",
        "Unexpected fees when adjusting my policy coverage",
        "Denied rental car reimbursement despite having coverage",
        "Frustrating automated phone system for claims support",
        "No response to my request for policy discount",
        "Incorrect information given about my coverage limits",
        
        # Business/Other insurance
        "Complicated policy renewal process",
        "Expensive premiums for basic coverage",
        "Technical issues with mobile app for policy management",
        "Inadequate business liability coverage options",
        "Disappointing pet insurance claim experience",
        "Travel insurance that had too many exclusions",
        "Rental insurance with confusing terms",
        "Cyber insurance with weak data breach support"
    ]
    
    # Expanded moods associated with sentiments
    positive_moods = ["satisfied", "happy", "impressed", "grateful", "relieved", "delighted", "pleased", "content", "appreciative", "optimistic"]
    negative_moods = ["frustrated", "disappointed", "annoyed", "angry", "concerned", "upset", "dissatisfied", "irritated", "discouraged", "skeptical"]

    # Determine number of reviews to generate in this run
    num_reviews = random.randint(min_reviews_per_run, max_reviews_per_run)
    logger.info(f"Generating {num_reviews} reviews")

    review_count = 0
    for _ in range(num_reviews):
        try:
            # Randomly select sentiment (positive or negative)
            sentiment = random.choice(["positive", "negative"])
            
            # Choose scenarios and moods based on sentiment
            if sentiment == "positive":
                scenario = random.choice(positive_scenarios)
                mood = random.choice(positive_moods)
            else:
                scenario = random.choice(negative_scenarios)
                mood = random.choice(negative_moods)
            
            # Generate a persona for this review
            persona = generate_persona()
            
            # Generate a detailed prompt with persona
            prompt = adapt_prompt_with_persona(scenario, sentiment, mood, persona)
            
            # Generate review content using Bedrock
            generation_result = bedrock_client.generate_content(prompt)
            
            # Extract the first generated review text
            review_text = generation_result["texts"][0] if generation_result["texts"] else ""
            
            # Clean up review text - remove any JSON or excessive quotes
            review_text = review_text.strip()
            
            # If it still looks like JSON or has excessive quotes, clean it
            if review_text.startswith('{') and review_text.endswith('}'):
                logger.info(f"Cleaning up JSON-like review text: {review_text[:100]}...")
                try:
                    # Try to parse as JSON and extract text
                    parsed = json.loads(review_text)
                    if isinstance(parsed, dict):
                        # Try to navigate nested content
                        if "output" in parsed and "message" in parsed["output"] and "content" in parsed["output"]["message"]:
                            content = parsed["output"]["message"]["content"]
                            if isinstance(content, list) and len(content) > 0 and "text" in content[0]:
                                review_text = content[0]["text"]
                except:
                    # If we can't parse it, just use as is
                    pass
            
            # Remove any excessive quotes
            if review_text.startswith('"') and review_text.endswith('"'):
                review_text = review_text[1:-1]
                
            # Create a review object
            review_id = str(uuid.uuid4())
            review_data = {
                "id": review_id,
                "text": review_text,
                "sentiment": sentiment,
                "scenario": scenario,
                "timestamp": datetime.utcnow().isoformat(),
                "source": "lambda_generator",
                "persona": {
                    "age": persona["age"],
                    "profession": persona["profession"],
                    "cultural_background": persona["cultural_background"]
                }
            }
            
            # Produce to Kafka
            producer.produce(
                kafka_topic_name,
                key=review_id,
                value=json.dumps(review_data)
            )
            producer.flush()
            
            logger.info(f"Review {review_id} ({sentiment}) produced to Kafka")
            review_count += 1
            
            # Add a small delay between reviews to avoid overloading the system
            if review_count < num_reviews:
                time.sleep(seconds_between_reviews)
                
        except Exception as e:
            logger.error(f"Error generating review: {e}")
    
    # Return a summary of the operation
    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": f"Successfully generated {review_count} reviews",
            "reviews_produced": review_count
        })
    } 