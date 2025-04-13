# Schema Registry Configuration

This directory contains the schema definitions used in the Confluent Schema Registry for the churn prevention project.

## Schema Files

- `policy_schema.json`: An Avro schema for the insurance policy data produced by the policy-producer Lambda function. This schema enforces the structure of the messages sent to the `policy-producer` Kafka topic.

## Schema Structure

The policy schema includes the following main sections:

1. **User Information**: Personal information about the policy holder (UserID, name, sex, birthdate, etc.)
2. **Address Information**: Address details including street, zip code, city, and geographic coordinates
3. **Car Information**: Details about the insured vehicle (make, model, year, etc.)
4. **Tariff Information**: Insurance coverage details stored in a nested structure
5. **Policy Information**: Policy status, start dates, claims history, etc.

## Schema Registry Usage

The Schema Registry ensures that all messages produced to Kafka topics conform to the registered schema, providing:

1. **Schema Validation**: Ensures data quality by validating messages against the schema before they're published
2. **Compatibility Checking**: Prevents breaking changes to schemas that would affect downstream consumers
3. **Schema Evolution**: Enables versioning and controlled evolution of schemas over time

## Updating Schemas

To update a schema:

1. Modify the schema file with your changes
2. Ensure the changes are compatible with existing schema versions
3. Update the Terraform configuration if necessary
4. Apply the changes with `terraform apply`

## Schema Registry Configuration

The Schema Registry configuration is managed in the main Terraform configuration. The important variables are:

- `schema_registry_id`: The ID of your Schema Registry instance
- `schema_registry_rest_endpoint`: The REST endpoint URL for your Schema Registry
- `policy_topic_name`: The Kafka topic name associated with this schema 