#!/bin/bash
set -e

# Check if DEBUG flag is set
if [ "$DEBUG" = "true" ]; then
  echo "Running in debug mode"
  set -x
fi

echo "Building customer-review-creator Lambda function..."

# Create a temporary directory for the build
rm -rf build
mkdir -p build

# Check for required files
if [ ! -f "requirements.txt" ]; then
  echo "ERROR: requirements.txt not found!"
  exit 1
fi

if [ ! -f "positive_scenarios.csv" ] || [ ! -f "negative_scenarios.csv" ]; then
  echo "ERROR: Scenario CSV files not found!"
  exit 1
fi

# Use Docker to build the package with all dependencies
# This uses the AWS Lambda Python runtime as the base image
docker run --rm -v $(pwd):/var/task --entrypoint=/bin/bash -w /var/task public.ecr.aws/lambda/python:3.11 \
  -c "
    # Install zip utility
    yum install -y zip
    
    # Install Python dependencies
    pip install --upgrade pip
    pip install -t /tmp/package -r requirements.txt
    
    # Copy function code and data
    cp -r *.py /tmp/package/
    cp -r *.csv /tmp/package/
    if [ -d \"input_data\" ]; then
      cp -r input_data /tmp/package/
    fi
    
    # Create zip package
    cd /tmp/package
    zip -r /var/task/deployment-package.zip .
  "

# Verify deployment package was created
if [ ! -f "deployment-package.zip" ]; then
  echo "ERROR: Failed to create deployment-package.zip"
  exit 1
fi

echo "Deployment package created: deployment-package.zip ($(du -h deployment-package.zip | cut -f1))"
echo "Package contents:"
unzip -l deployment-package.zip | head -n 10 