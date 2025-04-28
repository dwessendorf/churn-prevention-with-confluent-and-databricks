# Kafka GenAI Demo - Databricks App

This repository contains a Streamlit application for sentiment analysis of messages from Kafka, to be deployed as a Databricks Native Application.

## Prerequisites

1. Databricks CLI installed and configured
2. Access to a Databricks workspace
3. Appropriate permissions to create and deploy applications
4. Kafka cluster with configured topics and credentials

## App Structure

- `app.py` - Main Streamlit application
- `app.yaml` - Configuration for the Databricks App
- `requirements.txt` - Python dependencies
- `kafka_utils.py` - Kafka consumer and producer utilities
- `model_serving_utils.py` - Functions for querying model endpoints
- `deploy_app.sh` - Deployment script

## Secrets Setup

Before deploying, ensure the following secrets are set up in your Databricks workspace:

1. `bootstrap-servers` - Kafka bootstrap servers
2. `group-id` - Kafka consumer group ID
3. `input-secret-topic` - Kafka input topic
4. `output-secret-topic` - Kafka output topic
5. `model-endpoint` - Name of the model endpoint
6. `warehouse-id` - SQL warehouse ID
7. `username` - Kafka username (for SASL authentication)
8. `password` - Kafka password (for SASL authentication)
9. `sasl-mechanism` - Kafka SASL mechanism (typically PLAIN)
10. `security-protocol` - Kafka security protocol (typically SASL_SSL)

## Deployment

1. Make sure your Databricks CLI is configured:
   ```
   databricks configure
   ```

2. Run the deployment script:
   ```
   chmod +x deploy_app.sh
   ./deploy_app.sh
   ```

3. Or deploy manually:
   ```
   # Create workspace directory
   databricks workspace mkdirs /Workspace/Users/your-email/databricks_apps/kafka-genai-demo/streamlit-data-app
   
   # Sync files to workspace
   databricks workspace import_dir . /Workspace/Users/your-email/databricks_apps/kafka-genai-demo/streamlit-data-app --overwrite
   
   # Deploy the app
   databricks apps deploy kafka-genai-demo --source-code-path /Workspace/Users/your-email/databricks_apps/kafka-genai-demo/streamlit-data-app
   ```

## Viewing the App

After deployment, your app will be available in the Databricks UI under:
Compute > Apps > kafka-genai-demo

## Troubleshooting

If you encounter issues:

1. Check the app logs in the Databricks UI
2. Verify that all required secrets are properly configured
3. Ensure your Kafka cluster is accessible from Databricks
4. Confirm that the model endpoint exists and is properly configured 