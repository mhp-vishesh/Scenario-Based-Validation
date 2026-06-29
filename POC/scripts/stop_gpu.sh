#!/usr/bin/env bash
#
# Stop the GPU instance to halt compute billing.
#
# Usage:
#   bash POC/scripts/stop_gpu.sh
#
set -euo pipefail

INSTANCE_ID="${INSTANCE_ID:-i-0be9a4c24bbbcca2c}"
REGION="${REGION:-eu-central-1}"
PROFILE="${PROFILE:-poc}"
AWS="${AWS_BIN:-$HOME/aws-cli/aws}"

export AWS_PAGER=""

"$AWS" --profile "$PROFILE" --region "$REGION" ec2 stop-instances \
    --instance-ids "$INSTANCE_ID" \
    --query 'StoppingInstances[0].{Id:InstanceId,Now:CurrentState.Name}' \
    --output table
echo "Compute billing stops once state reaches 'stopped'. The EBS disk keeps a small storage charge."
