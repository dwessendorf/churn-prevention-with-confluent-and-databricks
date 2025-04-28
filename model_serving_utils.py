import os
import json
import requests
from typing import Dict, List, Any
from databricks.sdk.core import Config
from databricks.sdk.service import serving

def query_endpoint(endpoint_name: str, messages: List[Dict[str, str]], max_tokens: int = 500) -> Dict[str, Any]:
    """
    Query a Databricks model serving endpoint - handles both Databricks endpoints and Bedrock endpoints

    Args:
        endpoint_name: The name of the endpoint to query
        messages: List of message dicts with role and content
        max_tokens: Maximum number of tokens to generate

    Returns:
        Dict containing the model response
    """
    try:
        # Handle Bedrock endpoints (based on name convention)
        if endpoint_name.startswith("bedrock-"):
            # This is a special case for handling AWS Bedrock endpoints
            # In production, you would use boto3 to call Bedrock directly
            # For this app we simulate a response for a sentiment analysis task
            print(f"Simulating Bedrock endpoint call to {endpoint_name}")
            
            # Get the input text from the user message
            user_text = ""
            for msg in messages:
                if msg["role"] == "user":
                    # Extract text after the prompt
                    content = msg["content"]
                    if "Analyze the sentiment of this text:" in content:
                        user_text = content.split("Analyze the sentiment of this text:", 1)[1].strip()
                    break
            
            # Simple sentiment analysis simulation
            sentiment_score = 0.0
            sentiment_label = "neutral"
            
            # Very basic sentiment analysis based on keywords
            positive_words = ["good", "great", "excellent", "happy", "love", "best", "amazing", "awesome"]
            negative_words = ["bad", "terrible", "awful", "sad", "hate", "worst", "horrible", "disappointing"]
            
            # Count positive and negative words
            pos_count = sum(1 for word in positive_words if word in user_text.lower())
            neg_count = sum(1 for word in negative_words if word in user_text.lower())
            
            # Determine sentiment based on counts
            if pos_count > neg_count:
                sentiment_score = min(0.9, 0.3 + (0.2 * (pos_count - neg_count)))
                sentiment_label = "positive"
            elif neg_count > pos_count:
                sentiment_score = max(-0.9, -0.3 - (0.2 * (neg_count - pos_count)))
                sentiment_label = "negative"
            else:
                # Slightly random neutral sentiment
                import random
                sentiment_score = random.uniform(-0.2, 0.2)
                sentiment_label = "neutral"
            
            # Create response in the expected format
            response = {
                "choices": [{
                    "index": 0,
                    "finish_reason": "stop",
                }]
            }
            
            # Format response as JSON in content field
            sentiment_json = json.dumps({
                "sentiment_label": sentiment_label,
                "sentiment_score": sentiment_score
            }, indent=2)
            
            response["content"] = f"Based on my analysis, here's the sentiment evaluation:\n\n{sentiment_json}"
            return response
            
        # Standard Databricks serving endpoint
        else:
            cfg = Config()
            workspaceClient = serving.ServingEndpointClient(cfg)
            
            # Prepare the request payload based on model type
            payload = {
                "messages": messages,
                "max_tokens": max_tokens
            }
            
            # Call the endpoint
            response = workspaceClient.query(
                name=endpoint_name,
                dataframe_records=[payload]
            )
            
            # Extract and return the result
            return response.predictions[0]
            
    except Exception as e:
        print(f"Error calling model endpoint {endpoint_name}: {str(e)}")
        # Return a fallback response
        return {
            "content": json.dumps({
                "sentiment_label": "error",
                "sentiment_score": 0.0
            })
        } 