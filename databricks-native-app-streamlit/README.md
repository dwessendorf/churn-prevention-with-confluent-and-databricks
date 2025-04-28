# Kafka Sentiment Analysis Dashboard

This Streamlit application processes messages from a Kafka topic, performs sentiment analysis using a Databricks model endpoint, and displays real-time metrics in a dashboard. It also stores the processed messages in both Kafka and a Databricks Delta table.

## Features

- Real-time consumption of messages from a Kafka topic
- Sentiment analysis using Databricks model serving
- End-to-end latency tracking and reporting
- Live dashboard with metrics and visualizations
- Storage of processed messages in Kafka and Databricks Delta tables
- Secure Kafka authentication using SASL
- Configuration management using Databricks Secrets

## Requirements

- Databricks runtime
- A running Kafka cluster (Confluent Kafka)
- A deployed Databricks model endpoint for sentiment analysis
- Access to a Databricks SQL warehouse
- Kafka credentials if authentication is enabled

## Configuration

All sensitive configuration is managed through Databricks Secrets. Before running the application, you need to set up the following secrets in a secret scope called `kafka-app`:

### Required Secrets
```bash
# Create the secret scope (run once)
databricks secrets create-scope --scope kafka-app

# Set up required secrets
databricks secrets put --scope kafka-app --key warehouse-id --string-value "your-warehouse-id"
databricks secrets put --scope kafka-app --key bootstrap-servers --string-value "your-kafka-servers"
databricks secrets put --scope kafka-app --key input-topic --string-value "your-input-topic"
databricks secrets put --scope kafka-app --key output-topic --string-value "your-output-topic"
databricks secrets put --scope kafka-app --key group-id --string-value "your-group-id"
databricks secrets put --scope kafka-app --key model-endpoint --string-value "your-model-endpoint"

# Set up Kafka security secrets (if using authentication)
databricks secrets put --scope kafka-app --key security-protocol --string-value "SASL_SSL"
databricks secrets put --scope kafka-app --key sasl-mechanism --string-value "PLAIN"
databricks secrets put --scope kafka-app --key username --string-value "your-kafka-username"
databricks secrets put --scope kafka-app --key password --string-value "your-kafka-password"
```

The application's `app.yaml` file properly declares secret resources and then references them in the environment variables:

```yaml
# First define secret resources
resources:
  - name: kafka-app-warehouse-id
    type: secrets
    config:
      scope: kafka-app
      key: warehouse-id
  # Additional secret resources...

# Then reference them in environment variables
env:
  - name: DATABRICKS_WAREHOUSE_ID
    valueFrom: "kafka-app-warehouse-id"
  # Additional environment variables...
```

This two-step approach ensures that:
- Sensitive information is never stored in code
- Credentials can be rotated without code changes
- Access to secrets can be controlled through Databricks' permission system
- Different environments can use different credentials without code changes

### Secret Descriptions

#### Required Secrets
- `warehouse-id`: ID of your Databricks SQL warehouse
- `bootstrap-servers`: Kafka bootstrap servers (e.g., "server:9092")
- `input-topic`: Topic to consume messages from
- `output-topic`: Topic to send processed messages to
- `group-id`: Consumer group ID for the application (see Consumer Group ID Configuration below)
- `model-endpoint`: Name of your Databricks model endpoint for sentiment analysis

#### Kafka Security Secrets (Optional)
- `security-protocol`: Security protocol (e.g., "SASL_SSL", "SASL_PLAINTEXT")
- `sasl-mechanism`: SASL mechanism (e.g., "PLAIN", "SCRAM-SHA-256", "SCRAM-SHA-512")
- `username`: SASL username for authentication
- `password`: SASL password for authentication

### Consumer Group ID Configuration

The consumer group ID is a unique identifier you define for your application. It determines how your application processes messages in parallel and maintains offset tracking. Here's how to configure it:

#### Naming Convention
Use this format for your consumer group ID:
```
{app-name}-{environment}-{purpose}
```

Examples:
- Production: `sentiment-analysis-prod-processor`
- Development: `sentiment-analysis-dev-processor`
- Staging: `sentiment-analysis-staging-processor`

#### Important Considerations
1. **Uniqueness**: Each instance of your application that should process messages independently needs a different group ID
2. **Scaling**: Multiple instances with the same group ID will share the message processing load
3. **Testing**: Use different group IDs for testing to avoid interfering with production message processing
4. **Monitoring**: The group ID is used in Kafka monitoring tools to track consumer health and lag

#### Examples of Usage

1. **Single Instance Production**:
```bash
databricks secrets put --scope kafka-app --key group-id --string-value "sentiment-analysis-prod-processor"
```

2. **Multiple Environment Setup**:
```bash
# Development
databricks secrets put --scope kafka-app-dev --key group-id --string-value "sentiment-analysis-dev-processor"

# Staging
databricks secrets put --scope kafka-app-staging --key group-id --string-value "sentiment-analysis-staging-processor"

# Production
databricks secrets put --scope kafka-app-prod --key group-id --string-value "sentiment-analysis-prod-processor"
```

3. **Parallel Processing Setup**:
```bash
# For parallel processing instances
databricks secrets put --scope kafka-app --key group-id --string-value "sentiment-analysis-prod-processor-1"
databricks secrets put --scope kafka-app --key group-id --string-value "sentiment-analysis-prod-processor-2"
```

#### Best Practices
1. Use descriptive names that identify the application and its purpose
2. Include the environment (prod/dev/staging) in the group ID
3. Keep track of used group IDs to avoid conflicts
4. Document group ID assignments in your system documentation
5. Monitor consumer group lag using Kafka monitoring tools

### Secret Management Best Practices
1. Use different secret scopes for different environments (dev, staging, prod)
2. Regularly rotate credentials
3. Limit access to secrets using Databricks' ACLs
4. Audit secret access using Databricks' audit logs
5. Never store secrets in code or version control

### Troubleshooting Secret Configuration

If you encounter issues with secret configuration, check the following:

1. **Correct Resource and Reference Format**
   - Databricks native apps require two steps:
     - Define resources in the `resources` section
     - Reference those resources in the `env` section
   - The error `Error resolving resource` indicates a missing or improperly configured resource

2. **Resource Declaration**
   - Each secret must be declared as a resource before it can be used
   - Example:
     ```yaml
     resources:
       - name: kafka-app-password
         type: secrets
         config:
           scope: kafka-app
           key: password
     ```
   - Then referenced in env:
     ```yaml
     env:
       - name: KAFKA_SASL_PASSWORD
         valueFrom: "kafka-app-password"
     ```

3. **Secret Scope Existence**
   - Verify the secret scope exists: `databricks secrets list-scopes`
   - If missing, create it: `databricks secrets create-scope --scope kafka-app`

4. **Secret Availability**
   - Verify secrets exist in the scope: `databricks secrets list --scope kafka-app`
   - If missing, add them using the commands in the Required Secrets section

5. **Secret Access Permissions**
   - Ensure the service principal running the app has access to the secrets
   - Check ACLs: `databricks secrets list-acls --scope kafka-app`
   - Grant access if needed: `databricks secrets put-acl --scope kafka-app --principal <principal> --permission READ`

6. **Common Errors**
   - `Error resolving resource [resource-name]`: The resource doesn't exist in app.yaml
   - `Could not find secret value for key [key]`: The secret doesn't exist in the specified scope
   - `Access denied`: The service principal doesn't have permission to access the secret

7. **Environment-Specific Configuration**
   - For multi-environment deployments, ensure you're using the correct secret scope
   - Development, staging, and production should use separate scopes

## Input Message Format

The application expects JSON messages in the following format:

```json
{
  "id": "unique-message-id",
  "text": "The text to analyze for sentiment",
  "create_time": 1234567890.123 // Optional timestamp when the message was created
}
```

## Output Message Format

Processed messages will be sent to the output topic in the following format:

```json
{
  "message_id": "unique-message-id",
  "original_text": "The text that was analyzed",
  "processed_timestamp": "2023-01-01T12:00:00.000Z",
  "sentiment_score": 0.75,
  "sentiment_label": "positive",
  "processing_time_ms": 153.42,
  "total_latency_ms": 203.56
}
```

## Delta Table Schema

The application creates a Delta table named `sentiment_analysis_results` with the following schema:

- `message_id`: STRING
- `original_text`: STRING
- `processed_timestamp`: TIMESTAMP
- `sentiment_score`: DOUBLE
- `sentiment_label`: STRING
- `processing_time_ms`: DOUBLE

## Running the Application

The application runs as a Databricks native app. Deploy it according to the Databricks native app deployment procedures.

## Dashboard

The dashboard displays:

1. Average and maximum latency
2. Average sentiment score
3. Throughput (messages per minute)
4. Sentiment distribution chart
5. Latest processed messages
6. Table of recent messages with details

The dashboard refreshes automatically every 5 seconds. 