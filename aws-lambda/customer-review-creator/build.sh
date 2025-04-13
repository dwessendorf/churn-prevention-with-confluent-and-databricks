#!/bin/bash
set -e

# Create a temporary directory for the build
rm -rf build
mkdir -p build

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
      cp -r input_data /tmp/package/
    fi
    
    # Create zip package
    cd /tmp/package
    zip -r /var/task/deployment-package.zip .
  "

echo "Deployment package created: deployment-package.zip" 