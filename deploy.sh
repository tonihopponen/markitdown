#!/bin/bash

# MarkItDown Lambda Deployment Script
# This script builds and deploys the Lambda function to AWS

set -e  # Exit on any error

# Configuration
FUNCTION_NAME="markitdown-converter"
REGION="${AWS_REGION:-us-east-1}"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REPO="${FUNCTION_NAME}-repo"
IMAGE_TAG="latest"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Helper functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check if AWS CLI is installed
    if ! command -v aws &> /dev/null; then
        log_error "AWS CLI is not installed. Please install it first."
        exit 1
    fi
    
    # Check if Docker is installed
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed. Please install it first."
        exit 1
    fi
    
    # Check if user is authenticated with AWS
    if ! aws sts get-caller-identity &> /dev/null; then
        log_error "Not authenticated with AWS. Please run 'aws configure' first."
        exit 1
    fi
    
    log_info "Prerequisites check passed!"
}

# Create ECR repository if it doesn't exist
create_ecr_repo() {
    log_info "Creating ECR repository if it doesn't exist..."
    
    if ! aws ecr describe-repositories --repository-names "$ECR_REPO" --region "$REGION" &> /dev/null; then
        aws ecr create-repository --repository-name "$ECR_REPO" --region "$REGION"
        log_info "Created ECR repository: $ECR_REPO"
    else
        log_info "ECR repository already exists: $ECR_REPO"
    fi
}

# Build Docker image
build_image() {
    log_info "Building Docker image..."
    
    # Get ECR login token
    aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"
    
    # Build image
    docker build -t "$FUNCTION_NAME" .
    
    # Tag image for ECR
    docker tag "$FUNCTION_NAME:$IMAGE_TAG" "$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$ECR_REPO:$IMAGE_TAG"
    
    log_info "Docker image built successfully!"
}

# Push image to ECR
push_image() {
    log_info "Pushing image to ECR..."
    
    docker push "$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$ECR_REPO:$IMAGE_TAG"
    
    log_info "Image pushed to ECR successfully!"
}

# Create IAM role for Lambda if it doesn't exist
create_iam_role() {
    log_info "Creating IAM role for Lambda..."
    
    ROLE_NAME="${FUNCTION_NAME}-role"
    
    # Check if role exists
    if ! aws iam get-role --role-name "$ROLE_NAME" &> /dev/null; then
        # Create trust policy
        cat > trust-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF
        
        # Create role
        aws iam create-role --role-name "$ROLE_NAME" --assume-role-policy-document file://trust-policy.json
        
        # Attach basic execution policy
        aws iam attach-role-policy --role-name "$ROLE_NAME" --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
        
        # Clean up
        rm trust-policy.json
        
        log_info "Created IAM role: $ROLE_NAME"
    else
        log_info "IAM role already exists: $ROLE_NAME"
    fi
}

# Deploy Lambda function
deploy_lambda() {
    log_info "Deploying Lambda function..."
    
    ROLE_NAME="${FUNCTION_NAME}-role"
    ROLE_ARN="arn:aws:iam::$ACCOUNT_ID:role/$ROLE_NAME"
    IMAGE_URI="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$ECR_REPO:$IMAGE_TAG"
    
    # Check if function exists
    if aws lambda get-function --function-name "$FUNCTION_NAME" --region "$REGION" &> /dev/null; then
        log_info "Updating existing Lambda function..."
        aws lambda update-function-code \
            --function-name "$FUNCTION_NAME" \
            --image-uri "$IMAGE_URI" \
            --region "$REGION"
    else
        log_info "Creating new Lambda function..."
        aws lambda create-function \
            --function-name "$FUNCTION_NAME" \
            --package-type Image \
            --code ImageUri="$IMAGE_URI" \
            --role "$ROLE_ARN" \
            --timeout 900 \
            --memory-size 1024 \
            --region "$REGION"
    fi
    
    log_info "Lambda function deployed successfully!"
}

# Create API Gateway (optional)
create_api_gateway() {
    log_info "Creating API Gateway..."
    
    API_NAME="${FUNCTION_NAME}-api"
    
    # Create HTTP API
    API_ID=$(aws apigatewayv2 create-api \
        --name "$API_NAME" \
        --protocol-type HTTP \
        --target "arn:aws:lambda:$REGION:$ACCOUNT_ID:function:$FUNCTION_NAME" \
        --region "$REGION" \
        --query 'ApiId' \
        --output text)
    
    # Add Lambda permission
    aws lambda add-permission \
        --function-name "$FUNCTION_NAME" \
        --statement-id apigateway-invoke \
        --action lambda:InvokeFunction \
        --principal apigateway.amazonaws.com \
        --source-arn "arn:aws:execute-api:$REGION:$ACCOUNT_ID:$API_ID/*/*/*" \
        --region "$REGION"
    
    log_info "API Gateway created with ID: $API_ID"
    log_info "API Gateway URL: https://$API_ID.execute-api.$REGION.amazonaws.com/"
}

# Run tests
run_tests() {
    log_info "Running tests..."
    
    if python -m pytest test_lambda.py -v; then
        log_info "All tests passed!"
    else
        log_error "Tests failed! Please fix the issues before deploying."
        exit 1
    fi
}

# Main deployment function
main() {
    log_info "Starting deployment of $FUNCTION_NAME..."
    
    # Run all deployment steps
    check_prerequisites
    run_tests
    create_ecr_repo
    build_image
    push_image
    create_iam_role
    deploy_lambda
    
    # Ask user if they want to create API Gateway
    read -p "Do you want to create an API Gateway for this function? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        create_api_gateway
    fi
    
    log_info "Deployment completed successfully!"
    log_info "Function name: $FUNCTION_NAME"
    log_info "Region: $REGION"
}

# Handle command line arguments
case "${1:-deploy}" in
    "deploy")
        main
        ;;
    "test")
        run_tests
        ;;
    "build")
        build_image
        ;;
    "clean")
        log_info "Cleaning up..."
        docker rmi "$FUNCTION_NAME" 2>/dev/null || true
        docker rmi "$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$ECR_REPO:$IMAGE_TAG" 2>/dev/null || true
        log_info "Cleanup completed!"
        ;;
    *)
        echo "Usage: $0 {deploy|test|build|clean}"
        echo "  deploy - Full deployment (default)"
        echo "  test   - Run tests only"
        echo "  build  - Build Docker image only"
        echo "  clean  - Clean up Docker images"
        exit 1
        ;;
esac 