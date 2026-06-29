#!/usr/bin/env bash
#
# One command to bring the GPU instance back and start the real run.
#
# It does everything that has to happen after a stop/start:
#   1. Refresh the AWS SSO session if it expired.
#   2. Start the instance and wait until it is running.
#   3. Read the new public IP (it changes on every start).
#   4. Make sure your current home IP can reach SSH (22) and the dashboard (8501).
#   5. Re-apply the CUDA ldconfig fix (it does not survive a stop/start).
#   6. Launch the real generation + judge in the background, logging to ~/run.log.
#
# Usage (from anywhere):
#   bash POC/scripts/resume_gpu.sh
#
# Override any of these with environment variables if the setup changes:
#   INSTANCE_ID, REGION, PROFILE, AWS_BIN, SSH_USER, KEY, SG_ID
#
set -euo pipefail

INSTANCE_ID="${INSTANCE_ID:-i-0be9a4c24bbbcca2c}"
REGION="${REGION:-eu-central-1}"
PROFILE="${PROFILE:-poc}"
AWS="${AWS_BIN:-$HOME/aws-cli/aws}"
SSH_USER="${SSH_USER:-ubuntu}"
SG_ID="${SG_ID:-sg-08e80bc41d447dc68}"

export AWS_PAGER=""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
KEY="${KEY:-$ROOT/sbv-testing16062026.pem}"

aws_cli() { "$AWS" --profile "$PROFILE" --region "$REGION" "$@"; }
ssh_run() { ssh -i "$KEY" -o StrictHostKeyChecking=no "$SSH_USER@$IP" "$@"; }

if [ ! -f "$KEY" ]; then
    echo "SSH key not found at $KEY. Set KEY=/path/to/key.pem and retry." >&2
    exit 1
fi
chmod 400 "$KEY" 2>/dev/null || true

echo "== 1/6 Checking AWS SSO session =="
if ! aws_cli sts get-caller-identity >/dev/null 2>&1; then
    echo "SSO expired. Opening browser login..."
    "$AWS" sso login --profile "$PROFILE"
fi

echo "== 2/6 Starting instance $INSTANCE_ID =="
aws_cli ec2 start-instances --instance-ids "$INSTANCE_ID" >/dev/null
echo "Waiting for it to reach 'running'..."
aws_cli ec2 wait instance-running --instance-ids "$INSTANCE_ID"

echo "== 3/6 Reading public IP =="
IP="$(aws_cli ec2 describe-instances --instance-ids "$INSTANCE_ID" \
        --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)"
if [ -z "$IP" ] || [ "$IP" = "None" ]; then
    echo "Could not read a public IP. Is the instance configured for one?" >&2
    exit 1
fi
echo "Public IP: $IP"

echo "== 4/6 Allowing your current home IP through the firewall =="
MYIP="$(curl -s https://checkip.amazonaws.com | tr -d '[:space:]')"
if [ -n "$MYIP" ]; then
    for PORT in 22 8501; do
        aws_cli ec2 authorize-security-group-ingress \
            --group-id "$SG_ID" --protocol tcp --port "$PORT" \
            --cidr "$MYIP/32" >/dev/null 2>&1 \
            && echo "  added $MYIP/32 -> port $PORT" \
            || echo "  $MYIP/32 -> port $PORT already allowed"
    done
else
    echo "  could not detect your IP; skipping (SSH may fail if your IP changed)."
fi

echo "== Waiting for SSH to come up =="
for _ in $(seq 1 30); do
    if ssh -i "$KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=5 \
         "$SSH_USER@$IP" true 2>/dev/null; then
        echo "  SSH is up."
        break
    fi
    sleep 5
done

echo "== 5/6 Re-applying CUDA ldconfig fix =="
ssh_run 'find ~/POC/cosmos/Cosmos-Predict2.5/.venv/lib/python3.10/site-packages/nvidia \
            -maxdepth 2 -type d -name lib \
          | sudo tee /etc/ld.so.conf.d/cosmos-cuda.conf >/dev/null \
          && sudo ldconfig && echo "  ldconfig OK"'

echo "== 6/6 Launching real generation + judge in the background =="
ssh_run 'cd ~/POC && SKIP_PREDICT_ENV=1 SKIP_POC_ENV=1 SKIP_DOWNLOAD=1 \
            COSMOS_REASON_CHECKPOINT=$HOME/cosmos-models/reason-2-8b \
            nohup bash scripts/remote_run.sh > ~/run.log 2>&1 & echo "  STARTED pid $!"'

cat <<EOF

------------------------------------------------------------
Instance is up and the run is going. Public IP: $IP

Watch progress:
  ssh -i $KEY $SSH_USER@$IP 'tail -f ~/run.log'

Once the log says "Done. Manifest:", serve the dashboard:
  bash $SCRIPT_DIR/serve_dashboard.sh $IP
  then open  http://$IP:8501

Stop the instance when finished (stops billing):
  bash $SCRIPT_DIR/stop_gpu.sh
------------------------------------------------------------
EOF
