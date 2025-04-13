# Churn Prevention with Confluent and Databricks

This repository contains infrastructure and application code for a churn prevention system using Confluent Kafka and Databricks. The system processes customer reviews and policy data to help identify potential customer churn.

## Components

- **AWS Lambda Functions**: 
  - `customer-review-creator`: Generates synthetic customer reviews and publishes to Kafka
  - `policy-producer`: Generates policy data and publishes to Kafka

- **Terraform**: Infrastructure as Code for deploying the required resources on AWS and Confluent Cloud

## Getting Started

1. Set up credentials for AWS and Confluent Cloud
2. Update terraform.tfvars with your configuration
3. Run `terraform init` and `terraform apply` to deploy the infrastructure
4. Deploy Lambda functions using the provided build scripts

## Development

- Use the build scripts in the Lambda function directories to create deployment packages
- Test functions locally before deploying 