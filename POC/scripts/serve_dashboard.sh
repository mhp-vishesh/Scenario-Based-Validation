#!/usr/bin/env bash
#
# Serve the live dashboard FROM the GPU instance on port 8501.
# It reads ~/POC/outputs/manifest.json on the instance, so run it only after
# resume_gpu.sh has produced outputs (the run.log says "Done. Manifest:").
#
# Usage:
#   bash POC/scripts/serve_dashboard.sh <public-ip>
#
set -euo pipefail

IP="${1:-}"
if [ -z "$IP" ]; then
    echo "Usage: bash $0 <public-ip>" >&2
    exit 1
fi

SSH_USER="${SSH_USER:-ubuntu}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
KEY="${KEY:-$ROOT/sbv-testing16062026.pem}"

echo "Starting Streamlit on $IP:8501 ..."
ssh -i "$KEY" -o StrictHostKeyChecking=no "$SSH_USER@$IP" \
  'pkill -f "streamlit run" 2>/dev/null; sleep 1; \
   cd ~/POC && nohup ~/POC/.venv-gpu/bin/python -m streamlit run dashboard/app.py \
     --server.port 8501 --server.address 0.0.0.0 --server.headless true \
     > ~/dash.log 2>&1 & echo "STARTED pid $!"'

echo ""
echo "Dashboard: http://$IP:8501"
echo "Logs:      ssh -i $KEY $SSH_USER@$IP 'tail -f ~/dash.log'"
