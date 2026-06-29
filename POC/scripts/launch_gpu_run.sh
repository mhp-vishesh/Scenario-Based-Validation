#!/bin/bash
# Launch a single GPU instance for the real Cosmos generation + judge run.
#
# This provisions a g6e.xlarge (one NVIDIA L40S, 48 GB) in eu-central-1 and
# starts it. Starting the instance is the billable step. Nothing here runs
# automatically until you SSH in and call remote_run.sh.
#
# Re-auth first if your SSO session expired:
#   ~/aws-cli/aws sso login --profile poc
#
# Override any value with an env var, for example:
#   INSTANCE_TYPE=g6e.2xlarge ./scripts/launch_gpu_run.sh

set -euo pipefail

# ---- Configuration ---------------------------------------------------------
AWS="${AWS_BIN:-aws}"
PROFILE="${AWS_PROFILE:-poc}"
REGION="${AWS_REGION:-eu-central-1}"
INSTANCE_TYPE="${INSTANCE_TYPE:-g6e.xlarge}"   # 1x L40S 48GB, ~\$1-2/hr
KEY_NAME="${KEY_NAME:-cosmos-sbv-key}"
SECURITY_GROUP="${SECURITY_GROUP:-cosmos-sbv-sg}"
INSTANCE_NAME="${INSTANCE_NAME:-cosmos-sbv-gpu}"
ROOT_VOLUME_GB="${ROOT_VOLUME_GB:-300}"        # models (~50GB) + repos + outputs
# DLAMI owner account (Amazon). Used to resolve a current GPU driver AMI.
DLAMI_OWNER="${DLAMI_OWNER:-898082745236}"
AMI_NAME_FILTER="${AMI_NAME_FILTER:-Deep Learning Base OSS Nvidia Driver GPU AMI (Ubuntu 22.04)*}"

aws_cli() { "$AWS" --profile "$PROFILE" --region "$REGION" "$@"; }

echo "=========================================="
echo "Cosmos GPU run - launch"
echo "=========================================="
echo "Profile:       $PROFILE"
echo "Region:        $REGION"
echo "Instance type: $INSTANCE_TYPE"
echo ""

# ---- Preconditions ---------------------------------------------------------
if ! command -v "$AWS" &>/dev/null; then
    echo "Error: AWS CLI '$AWS' not found. Set AWS_BIN to its path."
    exit 1
fi

if ! aws_cli sts get-caller-identity &>/dev/null; then
    echo "Error: AWS credentials are not valid for profile '$PROFILE'."
    echo "Run: ~/aws-cli/aws sso login --profile $PROFILE"
    exit 1
fi
ACCOUNT_ID=$(aws_cli sts get-caller-identity --query Account --output text)
echo "AWS account: $ACCOUNT_ID"
echo ""

# ---- Resolve a current GPU AMI --------------------------------------------
if [ -n "${AMI_ID:-}" ]; then
    echo "Using AMI override: $AMI_ID"
else
    echo "Resolving the newest GPU driver AMI..."
    AMI_ID=$(aws_cli ec2 describe-images \
        --owners "$DLAMI_OWNER" \
        --filters "Name=name,Values=$AMI_NAME_FILTER" "Name=state,Values=available" \
        --query 'sort_by(Images, &CreationDate)[-1].ImageId' \
        --output text)
    if [ -z "$AMI_ID" ] || [ "$AMI_ID" = "None" ]; then
        echo "Error: could not resolve an AMI. Set AMI_ID explicitly."
        exit 1
    fi
    echo "Resolved AMI: $AMI_ID"
fi
echo ""

# ---- Key pair --------------------------------------------------------------
if ! aws_cli ec2 describe-key-pairs --key-names "$KEY_NAME" &>/dev/null; then
    echo "Creating key pair: $KEY_NAME"
    aws_cli ec2 create-key-pair \
        --key-name "$KEY_NAME" \
        --query 'KeyMaterial' \
        --output text > "${KEY_NAME}.pem"
    chmod 400 "${KEY_NAME}.pem"
    echo "Private key saved to ${KEY_NAME}.pem (keep it safe)"
else
    echo "Key pair '$KEY_NAME' already exists."
    if [ ! -f "${KEY_NAME}.pem" ]; then
        echo "Warning: ${KEY_NAME}.pem is not in this directory. You need it to SSH."
    fi
fi
echo ""

# ---- Security group --------------------------------------------------------
if ! aws_cli ec2 describe-security-groups --group-names "$SECURITY_GROUP" &>/dev/null; then
    echo "Creating security group: $SECURITY_GROUP"
    SG_ID=$(aws_cli ec2 create-security-group \
        --group-name "$SECURITY_GROUP" \
        --description "Cosmos SBV GPU run" \
        --query 'GroupId' --output text)
    MY_IP=$(curl -fsS https://checkip.amazonaws.com 2>/dev/null || echo "")
    CIDR="0.0.0.0/0"
    if [ -n "$MY_IP" ]; then CIDR="${MY_IP}/32"; fi
    echo "Allowing SSH (22) and Streamlit (8501) from $CIDR"
    aws_cli ec2 authorize-security-group-ingress \
        --group-id "$SG_ID" --protocol tcp --port 22 --cidr "$CIDR"
    aws_cli ec2 authorize-security-group-ingress \
        --group-id "$SG_ID" --protocol tcp --port 8501 --cidr "$CIDR"
    echo "Security group created: $SG_ID"
else
    SG_ID=$(aws_cli ec2 describe-security-groups \
        --group-names "$SECURITY_GROUP" \
        --query 'SecurityGroups[0].GroupId' --output text)
    echo "Using existing security group: $SG_ID"
fi
echo ""

# ---- Reuse a running instance if present ----------------------------------
EXISTING=$(aws_cli ec2 describe-instances \
    --filters "Name=tag:Name,Values=$INSTANCE_NAME" \
              "Name=instance-state-name,Values=running,pending" \
    --query 'Reservations[0].Instances[0].InstanceId' \
    --output text 2>/dev/null || echo "None")

if [ "$EXISTING" != "None" ] && [ -n "$EXISTING" ]; then
    INSTANCE_ID="$EXISTING"
    echo "Reusing running instance: $INSTANCE_ID"
else
    echo "Launching $INSTANCE_TYPE ..."
    INSTANCE_ID=$(aws_cli ec2 run-instances \
        --image-id "$AMI_ID" \
        --instance-type "$INSTANCE_TYPE" \
        --key-name "$KEY_NAME" \
        --security-group-ids "$SG_ID" \
        --block-device-mappings "[{\"DeviceName\":\"/dev/sda1\",\"Ebs\":{\"VolumeSize\":${ROOT_VOLUME_GB},\"VolumeType\":\"gp3\"}}]" \
        --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$INSTANCE_NAME}]" \
        --query 'Instances[0].InstanceId' --output text)
    echo "Instance launched: $INSTANCE_ID"
    echo "Waiting for it to reach 'running'..."
    aws_cli ec2 wait instance-running --instance-ids "$INSTANCE_ID"
fi

PUBLIC_IP=$(aws_cli ec2 describe-instances \
    --instance-ids "$INSTANCE_ID" \
    --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)

echo ""
echo "=========================================="
echo "Instance ready"
echo "=========================================="
echo "Instance ID: $INSTANCE_ID"
echo "Public IP:   $PUBLIC_IP"
echo ""
echo "1) Copy the project and seed to the instance:"
echo "   scp -i ${KEY_NAME}.pem -r ../POC ubuntu@${PUBLIC_IP}:~/POC"
echo ""
echo "2) SSH in:"
echo "   ssh -i ${KEY_NAME}.pem ubuntu@${PUBLIC_IP}"
echo ""
echo "3) On the instance, run the real generation + judge:"
echo "   cd ~/POC && ./scripts/remote_run.sh"
echo ""
echo "4) Copy the outputs back to your laptop:"
echo "   scp -i ${KEY_NAME}.pem -r ubuntu@${PUBLIC_IP}:~/POC/outputs ./outputs"
echo ""
echo "Cost note: $INSTANCE_TYPE is roughly \$1-2/hr. Stop it when idle:"
echo "   $AWS --profile $PROFILE --region $REGION ec2 stop-instances --instance-ids $INSTANCE_ID"
echo "Terminate it when done (deletes the instance and its disk):"
echo "   $AWS --profile $PROFILE --region $REGION ec2 terminate-instances --instance-ids $INSTANCE_ID"
echo ""
