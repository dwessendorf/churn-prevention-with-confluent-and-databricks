#!/bin/bash

# Script to deploy the Kafka GenAI demo app to Databricks

# Variables
APP_NAME="kafka-genai-demo"
WORKSPACE_PATH="/Workspace/Users/dwessendorf@confluent.io/databricks_apps/kafka-genai-demo_2025_04_10-14_08/streamlit-data-app"

# Echo the actions being performed
echo "Deploying $APP_NAME to Databricks Apps..."

# Create the target directory structure in the workspace if it doesn't exist
echo "Creating workspace directory structure..."
databricks workspace mkdirs $WORKSPACE_PATH

# Sync app files to the workspace
echo "Syncing app files to workspace..."
# Assuming current directory contains app.py, app.yaml, requirements.txt, etc.
databricks workspace import_dir . $WORKSPACE_PATH --overwrite

# Deploy the app
echo "Deploying app..."
databricks apps deploy $APP_NAME --source-code-path $WORKSPACE_PATH

echo "Deployment complete! Your app should now be available on Databricks."
echo "To view your app, navigate to Compute > Apps in the Databricks UI." 