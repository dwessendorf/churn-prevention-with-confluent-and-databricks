# Terraform AWS Lambda Deployment

This Terraform configuration deploys AWS Lambda functions that use AWS Bedrock to generate content and send it to Confluent Kafka topics.

## Prerequisites

- Terraform v1.0.0 or later
- AWS CLI configured with appropriate credentials
- Confluent Cloud account with environment and API keys
- Docker installed and running (required for building Lambda packages)
- Python 3.11 or later with pip

## Directory Structure

```
terraform/                  # Main Terraform directory
├── modules/                # Terraform modules
│   ├── aws_lambda/         # AWS Lambda module
│   └── confluent_cluster_aws/    # Confluent AWS cluster module
├── aws-lambda/             # Lambda function source code
│   ├── customer-review-creator/  # Customer review generator
│   └── policy-producer/         # Policy producer
├── main.tf                 # Main Terraform configuration
├── variables.tf            # Variable definitions
├── terraform.tfvars        # Variable values
└── outputs.tf              # Output definitions
```

## Configuration

Before deploying, update the `terraform.tfvars` file with your specific values:

```hcl
aws_region = "us-east-1"
confluent_environment_id = "env-your-environment-id"  # Replace with actual value
apikey_owner_id = "u-your-owner-id"  # Replace with actual value
confluent_cloud_api_key = "your-cloud-api-key"  # Replace with actual value
confluent_cloud_api_secret = "your-cloud-api-secret"  # Replace with actual value
```

## Prepare Lambda Deployment Packages

Before running Terraform, you need to build the Lambda deployment packages with all dependencies. This process requires Docker to ensure native extensions are compiled correctly for the Lambda environment:

1. Ensure Docker is running on your system

2. Build the customer-review-creator package:
   ```
   cd aws-lambda/customer-review-creator
   ./build.sh
   cd ../..
   ```

3. Build the policy-producer package:
   ```
   cd aws-lambda/policy-producer
   ./build.sh
   cd ../..
   ```

This creates `deployment-package.zip` files in each Lambda function directory containing all necessary code and dependencies properly compiled for the Lambda environment.

## Deployment Steps

1. Initialize Terraform:
   ```
   cd terraform
   terraform init
   ```

2. Validate the configuration:
   ```
   terraform validate
   ```

3. Preview the changes:
   ```
   terraform plan
   ```

4. Apply the configuration:
   ```
   terraform apply
   ```

5. Confirm by typing `yes` when prompted.

## Solution Overview

This deployment creates:

1. A single Confluent Kafka cluster on AWS with two topics:
   - `customer-reviews` - For customer review messages
   - `policy-producer` - For insurance policy messages

2. Two AWS Lambda functions:
   - `customer-review-creator` - Generates simulated customer reviews using AWS Bedrock
   - `policy-producer` - Generates simulated insurance policies using AWS Bedrock
   
Both Lambda functions connect to the same Confluent Kafka cluster but publish to different topics.

## Cleanup

To destroy all resources created by this configuration:

```
terraform destroy
```

## Troubleshooting

### Schema Registry Region Error

If you encounter a "Cannot find region" error when creating the Schema Registry, the configuration has been updated to use simply `aws` as the region ID rather than a specific AWS region. This is because Confluent Schema Registry has specific regional availability that may differ from standard AWS regions.

If you still encounter region issues, you may need to:
1. Check which regions are available for Schema Registry in your Confluent Cloud account
2. Update the region ID in `modules/confluent_environment/main.tf` to match an available region

### AWS Secrets Manager Errors

To avoid "already scheduled for deletion" errors with AWS Secrets Manager, the configuration now:
1. Uses `recovery_window_in_days = 0` to allow immediate deletion/recreation
2. Generates unique secret names with random suffixes to avoid name conflicts

If you're upgrading from a previous version of this code, you might need to manually delete existing secrets in the AWS console or wait for them to be fully deleted before applying again.

### Deprecated Resource Warning

The `confluent_schema_registry_cluster` resource is deprecated in the Confluent Terraform provider version 1.x and will be removed in version 2.0.0. This warning is expected and doesn't affect functionality. The configuration should be updated when upgrading to provider version 2.0.0. 