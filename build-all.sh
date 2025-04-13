#!/bin/bash
set -e

echo "Building all Lambda deployment packages..."

# Define Lambda function directories
LAMBDA_DIRS=(
  "aws-lambda/customer-review-creator"
  "aws-lambda/policy-producer"
)

# Check if DEBUG flag is set
if [ "$DEBUG" = "true" ]; then
  echo "Running in debug mode"
  set -x
fi

# Build each Lambda function
for dir in "${LAMBDA_DIRS[@]}"; do
  if [ -d "$dir" ]; then
    echo "========================================"
    echo "Building Lambda function in $dir"
    echo "========================================"
    
    # Navigate to the function directory
    cd "$dir"
    
    # Check if build script exists
    if [ ! -f "build.sh" ]; then
      echo "ERROR: build.sh not found in $dir"
      exit 1
    fi
    
    # Make build script executable if it isn't already
    chmod +x build.sh
    
    # Run the build script
    ./build.sh
    
    # Verify deployment package was created
    if [ ! -f "deployment-package.zip" ]; then
      echo "ERROR: Failed to create deployment-package.zip in $dir"
      exit 1
    fi
    
    # Go back to the root directory
    cd - > /dev/null
    echo "Successfully built Lambda function in $dir"
    echo ""
  else
    echo "WARNING: Directory $dir does not exist"
  fi
done

echo "Build process completed successfully!"
echo "Lambda function deployment packages:"
for dir in "${LAMBDA_DIRS[@]}"; do
  if [ -f "$dir/deployment-package.zip" ]; then
    echo "- $dir/deployment-package.zip ($(du -h "$dir/deployment-package.zip" | cut -f1))"
  fi
done

echo ""
echo "You can now deploy these packages using Terraform:"
echo "cd terraform && terraform apply" 