#!/bin/bash
# Setup AWS infrastructure for Cosmos model hosting.
# Prerequisites: AWS CLI configured with appropriate credentials.

set -euo pipefail

# Configuration
REGION="${AWS_REGION:-us-west-2}"
INSTANCE_TYPE="${INSTANCE_TYPE:-p4d.24xlarge}"
AMI_ID="${AMI_ID:-ami-0d8f6eb4f641ef691}"  # Deep Learning AMI
KEY_NAME="${KEY_NAME:-cosmos-poc-key}"
SECURITY_GROUP="${SECURITY_GROUP:-cosmos-poc-sg}"
INSTANCE_NAME="cosmos-sbv-poc"

echo "=========================================="
echo "Scenario-Based Validation AWS Setup"
echo "=========================================="
echo "Region: $REGION"
echo "Instance Type: $INSTANCE_TYPE"
echo ""

# Check AWS CLI
if ! command -v aws &> /dev/null; then
    echo "Error: AWS CLI not found. Install from https://aws.amazon.com/cli/"
    exit 1
fi

# Verify credentials
echo "Verifying AWS credentials..."
if ! aws sts get-caller-identity &> /dev/null; then
    echo "Error: AWS credentials not configured. Run 'aws configure' first."
    exit 1
fi
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "Using AWS Account: $ACCOUNT_ID"
echo ""

# Create key pair if needed
if ! aws ec2 describe-key-pairs --key-names "$KEY_NAME" --region "$REGION" &> /dev/null; then
    echo "Creating key pair: $KEY_NAME"
    aws ec2 create-key-pair \
        --key-name "$KEY_NAME" \
        --region "$REGION" \
        --query 'KeyMaterial' \
        --output text > "${KEY_NAME}.pem"
    chmod 400 "${KEY_NAME}.pem"
    echo "Key pair saved to ${KEY_NAME}.pem"
else
    echo "Key pair '$KEY_NAME' already exists"
fi
echo ""

# Create security group if needed
if ! aws ec2 describe-security-groups --group-names "$SECURITY_GROUP" --region "$REGION" &> /dev/null; then
    echo "Creating security group: $SECURITY_GROUP"
    SG_ID=$(aws ec2 create-security-group \
        --group-name "$SECURITY_GROUP" \
        --description "Security group for Cosmos POC" \
        --region "$REGION" \
        --query 'GroupId' \
        --output text)
    
    # Allow SSH
    aws ec2 authorize-security-group-ingress \
        --group-id "$SG_ID" \
        --protocol tcp \
        --port 22 \
        --cidr 0.0.0.0/0 \
        --region "$REGION"
    
    # Allow Streamlit (8501)
    aws ec2 authorize-security-group-ingress \
        --group-id "$SG_ID" \
        --protocol tcp \
        --port 8501 \
        --cidr 0.0.0.0/0 \
        --region "$REGION"
    
    echo "Security group created: $SG_ID"
else
    SG_ID=$(aws ec2 describe-security-groups \
        --group-names "$SECURITY_GROUP" \
        --region "$REGION" \
        --query 'SecurityGroups[0].GroupId' \
        --output text)
    echo "Using existing security group: $SG_ID"
fi
echo ""

# Check for existing instance
EXISTING=$(aws ec2 describe-instances \
    --filters "Name=tag:Name,Values=$INSTANCE_NAME" "Name=instance-state-name,Values=running,pending" \
    --region "$REGION" \
    --query 'Reservations[0].Instances[0].InstanceId' \
    --output text 2>/dev/null || echo "None")

if [ "$EXISTING" != "None" ] && [ -n "$EXISTING" ]; then
    echo "Found existing instance: $EXISTING"
    PUBLIC_IP=$(aws ec2 describe-instances \
        --instance-ids "$EXISTING" \
        --region "$REGION" \
        --query 'Reservations[0].Instances[0].PublicIpAddress' \
        --output text)
    echo "Public IP: $PUBLIC_IP"
else
    echo "Launching new EC2 instance..."
    echo "Instance type: $INSTANCE_TYPE"
    echo "This may take a few minutes..."
    
    # User data script for initial setup
    USER_DATA=$(cat << 'EOF'
#!/bin/bash
set -e

# Update system
sudo apt-get update -y

# Install Docker if not present
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker ubuntu
fi

# Install NVIDIA Container Toolkit
if ! command -v nvidia-ctk &> /dev/null; then
    distribution=$(. /etc/os-release; echo $ID$VERSION_ID)
    curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
    curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list
    sudo apt-get update
    sudo apt-get install -y nvidia-container-toolkit
    sudo nvidia-ctk runtime configure --runtime=docker
    sudo systemctl restart docker
fi

# Clone the POC repository
cd /home/ubuntu
if [ ! -d "Scenario-Based-Validation" ]; then
    git clone https://github.com/mhp-vishesh/Scenario-Based-Validation.git
fi

# Create model storage directory
sudo mkdir -p /opt/cosmos/models
sudo chown ubuntu:ubuntu /opt/cosmos/models

echo "Setup complete!" > /home/ubuntu/setup_complete.txt
EOF
    )
    
    INSTANCE_ID=$(aws ec2 run-instances \
        --image-id "$AMI_ID" \
        --instance-type "$INSTANCE_TYPE" \
        --key-name "$KEY_NAME" \
        --security-group-ids "$SG_ID" \
        --user-data "$USER_DATA" \
        --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$INSTANCE_NAME}]" \
        --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":500,"VolumeType":"gp3"}}]' \
        --region "$REGION" \
        --query 'Instances[0].InstanceId' \
        --output text)
    
    echo "Instance launched: $INSTANCE_ID"
    echo "Waiting for instance to be running..."
    
    aws ec2 wait instance-running --instance-ids "$INSTANCE_ID" --region "$REGION"
    
    PUBLIC_IP=$(aws ec2 describe-instances \
        --instance-ids "$INSTANCE_ID" \
        --region "$REGION" \
        --query 'Reservations[0].Instances[0].PublicIpAddress' \
        --output text)
fi

echo ""
echo "=========================================="
echo "Setup Complete"
echo "=========================================="
echo ""
echo "Instance IP: $PUBLIC_IP"
echo ""
echo "Connect via SSH:"
echo "  ssh -i ${KEY_NAME}.pem ubuntu@$PUBLIC_IP"
echo ""
echo "After connecting, run:"
echo "  cd Scenario-Based-Validation"
echo "  ./scripts/pull_models.sh"
echo ""
echo "Estimated costs (us-west-2):"
echo "  p4d.24xlarge: ~\$32.77/hour"
echo "  p5.48xlarge:  ~\$98.32/hour (H100)"
echo "  g6e.xlarge:   ~\$1.08/hour (judge workloads)"
echo ""
echo "Remember to stop the instance when not in use:"
echo "  aws ec2 stop-instances --instance-ids $INSTANCE_ID --region $REGION"
