#!/bin/bash

# Setup OIDC for GitHub Actions AWS Authentication
# This script creates the necessary IAM resources for secure GitHub Actions deployment

set -e

# Configuration
GITHUB_REPO="tonihopponen/markitdown"  # Replace with your repo
AWS_REGION="${AWS_REGION:-us-east-1}"
ROLE_NAME="github-actions-oidc-role"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

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
    
    if ! command -v aws &> /dev/null; then
        log_error "AWS CLI is not installed."
        exit 1
    fi
    
    if ! aws sts get-caller-identity &> /dev/null; then
        log_error "Not authenticated with AWS. Please run 'aws configure' first."
        exit 1
    fi
    
    log_info "Prerequisites check passed!"
}

# Create OIDC identity provider
create_oidc_provider() {
    log_info "Creating OIDC identity provider..."
    
    # Check if provider already exists
    if aws iam get-open-id-connect-provider --open-id-connect-provider-arn "arn:aws:iam::$(aws sts get-caller-identity --query Account --output text):oidc-provider/token.actions.githubusercontent.com" &> /dev/null; then
        log_info "OIDC provider already exists"
        return
    fi
    
    # Create the OIDC provider
    aws iam create-open-id-connect-provider \
        --url https://token.actions.githubusercontent.com \
        --client-id-list sts.amazonaws.com \
        --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1
    
    log_info "OIDC provider created successfully!"
}

# Create IAM role for GitHub Actions
create_iam_role() {
    log_info "Creating IAM role for GitHub Actions..."
    
    # Check if role exists
    if aws iam get-role --role-name "$ROLE_NAME" &> /dev/null; then
        log_info "IAM role already exists: $ROLE_NAME"
        return
    fi
    
    # Create trust policy
    cat > trust-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::$(aws sts get-caller-identity --query Account --output text):oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:$GITHUB_REPO:*"
        }
      }
    }
  ]
}
EOF
    
    # Create role
    aws iam create-role \
        --role-name "$ROLE_NAME" \
        --assume-role-policy-document file://trust-policy.json
    
    # Create policy for Lambda and ECR access
    cat > lambda-ecr-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "lambda:UpdateFunctionCode",
        "lambda:GetFunction",
        "lambda:GetFunctionConfiguration"
      ],
      "Resource": "arn:aws:lambda:*:$(aws sts get-caller-identity --query Account --output text):function:markitdown-converter*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken",
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage",
        "ecr:PutImage",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:*:$(aws sts get-caller-identity --query Account --output text):log-group:/aws/lambda/*"
    }
  ]
}
EOF
    
    # Attach policy to role
    aws iam put-role-policy \
        --role-name "$ROLE_NAME" \
        --policy-name "LambdaECRAccess" \
        --policy-document file://lambda-ecr-policy.json
    
    # Clean up
    rm trust-policy.json lambda-ecr-policy.json
    
    log_info "IAM role created successfully: $ROLE_NAME"
}

# Display setup instructions
display_instructions() {
    ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
    ROLE_ARN="arn:aws:iam::$ACCOUNT_ID:role/$ROLE_NAME"
    
    log_info "Setup completed successfully!"
    echo
    log_info "Next steps:"
    echo "1. Go to your GitHub repository: https://github.com/$GITHUB_REPO"
    echo "2. Go to Settings → Secrets and variables → Actions"
    echo "3. Add the following repository secrets:"
    echo "   - AWS_ROLE_ARN: $ROLE_ARN"
    echo "   - AWS_REGION: $AWS_REGION"
    echo "4. Remove the old secrets (if any):"
    echo "   - AWS_ACCESS_KEY_ID"
    echo "   - AWS_SECRET_ACCESS_KEY"
    echo
    log_info "The workflow will now use secure OIDC authentication instead of access keys!"
}

# Main function
main() {
    log_info "Setting up OIDC authentication for GitHub Actions..."
    
    check_prerequisites
    create_oidc_provider
    create_iam_role
    display_instructions
}

# Run main function
main 