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
4. Build and deploy Lambda functions using the build functions described below

## Build Functions

The repository includes build scripts for creating AWS Lambda deployment packages. These scripts use Docker to ensure consistent environments and dependencies.

### Building Lambda Functions

#### Option 1: Build Individual Functions

To build either of the Lambda functions:

```bash
# For customer-review-creator function
cd aws-lambda/customer-review-creator
./build.sh

# For policy-producer function
cd aws-lambda/policy-producer
./build.sh
```

#### Option 2: Build All Functions

To build all Lambda functions at once:

```bash
# From the project root
./build-all.sh
```

### Build Process Details

The build scripts:

1. Create a temporary build directory
2. Use Docker with AWS Lambda Python 3.11 runtime container
3. Install required dependencies from `requirements.txt`
4. Package function code and data files
5. Create a deployment-ready ZIP file

#### Requirements

- Docker installed and running
- AWS CLI configured with appropriate credentials
- Bash shell

## Deployment

After building the Lambda deployment packages:

1. Verify deployment packages were created:
   ```bash
   ls -la aws-lambda/customer-review-creator/deployment-package.zip
   ls -la aws-lambda/policy-producer/deployment-package.zip
   ```

2. Deploy using Terraform:
   ```bash
   cd terraform
   terraform apply
   ```

## Debugging Build Issues

If you encounter issues building the Lambda functions:

- Ensure Docker is running
- Check that all required data files are in place:
  - For customer-review-creator: `positive_scenarios.csv` and `negative_scenarios.csv`
  - For policy-producer: The `input_data` directory and its contents
- Inspect build logs for specific error messages
- Try building with verbose output:
  ```bash
  DEBUG=true ./build.sh
  ```

## Development

- Test functions locally before deploying
- Use the AWS Lambda console to monitor function logs
- For local testing, you can use the AWS SAM CLI

## Cleanup

To clean up all resources:

```bash
cd terraform
terraform destroy
``` 