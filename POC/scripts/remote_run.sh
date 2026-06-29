#!/bin/bash
# Run the real Cosmos generation + Reason judge on the GPU instance.
#
# Run this ON the g6e instance, from the POC directory:
#   cd ~/POC && ./scripts/remote_run.sh
#
# It sets up two environments and then runs run_demo.py so the actors are
# synthesized and the judge scores them.
#
#   1) A uv environment inside cosmos/Cosmos-Predict2.5 for video generation.
#   2) A Python venv for the POC (YOLO, Streamlit) that also hosts the
#      in-process Cosmos-Reason judge (transformers + torch).
#
# Stages can be skipped once done:
#   SKIP_PREDICT_ENV=1 SKIP_POC_ENV=1 SKIP_DOWNLOAD=1 ./scripts/remote_run.sh

set -euo pipefail

POC_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$POC_DIR"

PREDICT_REPO="$POC_DIR/cosmos/Cosmos-Predict2.5"
MODELS_DIR="${MODELS_DIR:-$HOME/cosmos-models}"
SEED="${SEED:-seeds/20151221120048-D6-AGGRESSIVE-MOTORWAY.mp4}"
OUTPUT="${OUTPUT:-outputs/}"

# uv installs to ~/.local/bin; make sure it is on PATH even when Stage 1 is
# skipped, otherwise the generation subprocess cannot find "uv".
export PATH="$HOME/.local/bin:$PATH"

# Model choices. 2B/post-trained fits a single L40S 48GB comfortably.
# 14B/post-trained needs offloading on 48GB; prefer a bigger instance for it.
export COSMOS_PREDICT_MODEL="${COSMOS_PREDICT_MODEL:-2B/post-trained}"
export COSMOS_REASON_CHECKPOINT="${COSMOS_REASON_CHECKPOINT:-nvidia/Cosmos-Reason2-8B}"
# The cu128 flash-attn/cosmos_cuda wheels are built for Python 3.10 only.
COSMOS_CUDA_EXTRA="${COSMOS_CUDA_EXTRA:-cu128}"
COSMOS_PYTHON_VERSION="${COSMOS_PYTHON_VERSION:-3.10}"
# Fit the 2B pipeline on a 24GB GPU (A10G): offload one-shot components to CPU
# and reduce allocator fragmentation. Set COSMOS_PREDICT_LOWVRAM=0 on a big GPU.
export COSMOS_PREDICT_LOWVRAM="${COSMOS_PREDICT_LOWVRAM:-1}"
export PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}"

echo "=========================================="
echo "Cosmos real run"
echo "=========================================="
if command -v nvidia-smi &>/dev/null; then
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
else
    echo "Error: no GPU detected. This script must run on the GPU instance."
    exit 1
fi
echo "Predict model: $COSMOS_PREDICT_MODEL"
echo "Judge model:   $COSMOS_REASON_CHECKPOINT"
echo ""

# ---- Stage 1: Cosmos Predict environment (uv) ------------------------------
if [ "${SKIP_PREDICT_ENV:-0}" != "1" ]; then
    echo "[1/4] Setting up the Cosmos Predict environment with uv..."
    if ! command -v uv &>/dev/null; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
        export PATH="$HOME/.local/bin:$PATH"
    fi
    # Pin to Python 3.10 (cu128 wheels are cp310 only) and install the CUDA extra.
    echo "$COSMOS_PYTHON_VERSION" > "$PREDICT_REPO/.python-version"
    ( cd "$PREDICT_REPO" && uv sync --extra "$COSMOS_CUDA_EXTRA" --python "$COSMOS_PYTHON_VERSION" )
else
    echo "[1/4] Skipping Predict environment setup."
fi
export COSMOS_PREDICT_REPO="$PREDICT_REPO"
# Always activate the CUDA extra so cosmos_cuda stays present on every uv run.
export COSMOS_PREDICT_PYTHON="uv run --extra $COSMOS_CUDA_EXTRA python"
echo ""

# ---- Stage 2: POC + judge environment --------------------------------------
VENV="$POC_DIR/.venv-gpu"
if [ "${SKIP_POC_ENV:-0}" != "1" ]; then
    echo "[2/4] Setting up the POC + judge Python environment..."
    python3 -m venv "$VENV"
    # shellcheck disable=SC1091
    source "$VENV/bin/activate"
    pip install -q --upgrade pip
    # CUDA torch, a transformers build with Qwen3-VL support, and POC deps.
    pip install -q torch torchvision --index-url https://download.pytorch.org/whl/cu124
    pip install -q "transformers>=4.57" accelerate qwen-vl-utils
    pip install -q ultralytics opencv-python-headless imageio "imageio[ffmpeg]" \
                   streamlit pyyaml pillow numpy
else
    echo "[2/4] Skipping POC environment setup."
    # shellcheck disable=SC1091
    source "$VENV/bin/activate"
fi
echo ""

# ---- Stage 3: Download model weights ---------------------------------------
if [ "${SKIP_DOWNLOAD:-0}" != "1" ]; then
    echo "[3/4] Downloading model weights to $MODELS_DIR ..."
    mkdir -p "$MODELS_DIR"
    pip install -q huggingface_hub
    # The current CLI is "hf"; log in beforehand so this stage is non-interactive.
    if ! hf auth whoami &>/dev/null; then
        echo "Not logged in to HuggingFace. Run 'hf auth login' first (token is a secret)."
        exit 1
    fi
    # Generation weights (2B variant by default).
    hf download nvidia/Cosmos-Predict2.5-2B \
        --local-dir "$MODELS_DIR/predict-2.5-2b"
    # Judge weights are pulled by transformers on first use, cached under ~/.cache.
    hf download "$COSMOS_REASON_CHECKPOINT" \
        --local-dir "$MODELS_DIR/reason-2-8b"
    export COSMOS_REASON_CHECKPOINT="$MODELS_DIR/reason-2-8b"
else
    echo "[3/4] Skipping model download."
fi
echo ""

# ---- Stage 4: Real run -----------------------------------------------------
echo "[4/4] Running the real generation + judge..."
python scripts/run_demo.py --seed "$SEED" --output "$OUTPUT"

echo ""
echo "Done. Outputs are in $OUTPUT (manifest.json, clips/, sut/)."
echo "Copy them back to your laptop, then open the dashboard locally:"
echo "  scp -i <key>.pem -r ubuntu@<ip>:~/POC/outputs ./outputs"
echo "  ../.venv/bin/python -m streamlit run dashboard/app.py --server.port 8502"
