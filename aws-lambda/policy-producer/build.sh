#!/bin/bash
set -e

# Check if DEBUG flag is set
if [ "$DEBUG" = "true" ]; then
  echo "Running in debug mode"
  set -x
fi

echo "Building policy-producer Lambda function..."

# Create a temporary directory for the build
rm -rf build
mkdir -p build

# Check for required files
if [ ! -f "requirements.txt" ]; then
  echo "ERROR: requirements.txt not found!"
  exit 1
fi

# Check if input_data directory exists
if [ ! -d "input_data" ]; then
  echo "ERROR: input_data directory not found!"
  echo "Current directory: $(pwd)"
  echo "Files in current directory: $(ls -la)"
  exit 1
fi

echo "Input data directory exists with files:"
ls -la input_data/

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
    if [ -d \"input_data\" ]; then
      echo \"Copying input_data directory to package\"
      mkdir -p /tmp/package/input_data
      cp -r input_data/* /tmp/package/input_data/
      echo \"Files in /tmp/package/input_data:\"
      ls -la /tmp/package/input_data/
    else
      echo \"WARNING: input_data directory not found inside container\"
      exit 1
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
echo "Package contents (showing input_data entries):"
unzip -l deployment-package.zip | grep input_data 