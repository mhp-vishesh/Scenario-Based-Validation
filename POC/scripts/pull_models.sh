#!/bin/bash
# Pull Cosmos model checkpoints and repositories.
# Run this on the AWS instance after setup.

set -euo pipefail

MODELS_DIR="${MODELS_DIR:-/opt/cosmos/models}"
REPOS_DIR="${REPOS_DIR:-./cosmos}"

echo "=========================================="
echo "Cosmos Model Setup"
echo "=========================================="
echo ""

# Check for GPU
if command -v nvidia-smi &> /dev/null; then
    echo "GPU detected:"
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
    echo ""
else
    echo "Warning: No NVIDIA GPU detected. Models will not run efficiently."
    echo ""
fi

# Check for HuggingFace CLI
if ! command -v huggingface-cli &> /dev/null; then
    echo "Installing HuggingFace CLI..."
    pip install -q huggingface_hub[cli]
fi

# Check HF login
if ! huggingface-cli whoami &> /dev/null; then
    echo ""
    echo "HuggingFace authentication required."
    echo "Get your token from: https://huggingface.co/settings/tokens"
    echo ""
    huggingface-cli login
fi

echo ""
echo "Creating directories..."
mkdir -p "$MODELS_DIR"
mkdir -p "$REPOS_DIR"

# Clone Cosmos repositories
echo ""
echo "=========================================="
echo "Cloning Cosmos Repositories"
echo "=========================================="

COSMOS_REPOS=(
    "nvidia-cosmos/Cosmos-Predict2.5"
    "nvidia-cosmos/Cosmos-Transfer2.5"
    "nvidia-cosmos/Cosmos-Reason2"
)

for repo in "${COSMOS_REPOS[@]}"; do
    repo_name=$(basename "$repo")
    if [ -d "$REPOS_DIR/$repo_name" ]; then
        echo "Repository $repo_name already exists, pulling updates..."
        cd "$REPOS_DIR/$repo_name"
        git pull
        cd - > /dev/null
    else
        echo "Cloning $repo..."
        git clone "https://github.com/$repo.git" "$REPOS_DIR/$repo_name"
    fi
done

# Download model checkpoints
echo ""
echo "=========================================="
echo "Downloading Model Checkpoints"
echo "=========================================="
echo ""
echo "This will download several large files (~50GB total)."
echo "Make sure you have accepted model access on HuggingFace (instant auto-approval):"
echo "  - https://huggingface.co/nvidia/Cosmos-Predict2.5-14B"
echo "  - https://huggingface.co/nvidia/Cosmos-Transfer2.5-2B"
echo "  - https://huggingface.co/nvidia/Cosmos-Reason2-8B"
echo ""
read -p "Continue? (y/n) " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Skipping checkpoint download. You can run this script again later."
    exit 0
fi

# Cosmos Predict 2.5 (generation - open access)
echo ""
echo "Downloading Cosmos Predict 2.5 14B..."
huggingface-cli download nvidia/Cosmos-Predict2.5-14B \
    --local-dir "$MODELS_DIR/predict-2.5-14b" \
    --resume-download

# Cosmos Transfer 2.5 (generation - auto-gated)
echo ""
echo "Downloading Cosmos Transfer 2.5 2B..."
huggingface-cli download nvidia/Cosmos-Transfer2.5-2B \
    --local-dir "$MODELS_DIR/transfer-2.5-2b" \
    --resume-download

# Cosmos Reason 2 (judge model - auto-gated)
echo ""
echo "Downloading Cosmos Reason 2 8B..."
huggingface-cli download nvidia/Cosmos-Reason2-8B \
    --local-dir "$MODELS_DIR/reason-2-8b" \
    --resume-download

echo ""
echo "=========================================="
echo "Setup Complete"
echo "=========================================="
echo ""
echo "Model checkpoints saved to: $MODELS_DIR"
ls -la "$MODELS_DIR"
echo ""
echo "Cosmos repositories cloned to: $REPOS_DIR"
ls -la "$REPOS_DIR"
echo ""
echo "Next steps:"
echo "  1. Install Python dependencies:"
echo "     pip install -r requirements.txt"
echo ""
echo "  2. Set environment variables:"
echo "     export COSMOS_PREDICT_CHECKPOINT=$MODELS_DIR/predict-2.5-14b"
echo "     export COSMOS_TRANSFER_CHECKPOINT=$MODELS_DIR/transfer-2.5-2b"
echo "     export COSMOS_REASON_CHECKPOINT=$MODELS_DIR/reason-2-8b"
echo ""
echo "  3. Run the generation pipeline:"
echo "     python scripts/generate.py --seeds seeds/ --matrix config/scenario_matrix.yaml --output outputs/"
echo ""
echo "  4. Run validation:"
echo "     python scripts/validate.py --clips outputs/ --manifest outputs/manifest.json --rubric config/judge_rubric.yaml"
