#!/bin/bash

cd aws-lambda/policy-producer
./build.sh
cd ../../aws-lambda/customer-review-creator
./build.sh
cd ../..
cd terraform
terraform init
terraform apply -auto-approve
cd .. 