# Scenario-Based Validation POC

Closed-loop synthetic scenario generation and automated safety validation for ADAS, built on NVIDIA Cosmos and AWS.

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/mhp-vishesh/Scenario-Based-Validation?quickstart=1)

## Run from GitHub (no local setup)

**Option 1: GitHub Codespaces (recommended)**
1. Click the badge above or go to the repo and click **Code > Codespaces > Create codespace on main**
2. Wait for the environment to build (about 2 minutes)
3. Run in the terminal:
   ```bash
   streamlit run POC/dashboard/app.py
   ```
4. Click the forwarded port link (8501) when it appears

**Option 2: One-liner clone and run**
```bash
git clone https://github.com/mhp-vishesh/Scenario-Based-Validation.git && cd Scenario-Based-Validation && pip install -r POC/requirements.txt && MOCK_MODE=true streamlit run POC/dashboard/app.py
```

---

## What this does

1. Takes a small set of real or simulated driving clips (seed clips).
2. Fans them out into hundreds of edge-case variants using Cosmos Predict and Cosmos Transfer (weather, lighting, actor behaviour, occlusions).
3. Runs a system under test (a perception or planning model) on every variant.
4. Uses Cosmos Reason as an automated judge to score each clip and explain failures.
5. Surfaces results in a Streamlit dashboard with a coverage heatmap, failure gallery, and a one-page validation report export.

The goal: find failure modes the test fleet never encountered, with no extra data collection.

---

## Repository structure

```
.
├── README.md                 # This file
├── .devcontainer/            # GitHub Codespaces config
├── POC/
│   ├── config/
│   │   ├── scenario_matrix.yaml  # Axes for scenario fan-out
│   │   └── judge_rubric.yaml     # Rubric for Cosmos Reason verdicts
│   ├── scripts/
│   │   ├── setup_aws.sh          # Instance launch and bootstrap
│   │   ├── pull_models.sh        # Download model checkpoints
│   │   ├── generate.py           # Batch scenario generation
│   │   ├── validate.py           # Run system under test + judge
│   │   └── export_report.py      # Generate PDF report
│   ├── src/
│   │   ├── cosmos_wrapper.py     # Cosmos model wrappers
│   │   ├── judge.py              # Cosmos Reason judge
│   │   ├── evaluator.py          # Realism scoring
│   │   ├── manifest.py           # Manifest helpers
│   │   └── utils.py              # Shared utilities
│   ├── dashboard/
│   │   ├── app.py                # Streamlit dashboard
│   │   └── mock_data/            # Sample data for demo mode
│   ├── cosmos/                   # NVIDIA Cosmos submodules
│   │   ├── Cosmos-Predict2.5/
│   │   ├── Cosmos-Transfer2.5/
│   │   └── Cosmos-Reason1/
│   ├── tests/                    # Unit tests
│   ├── requirements.txt          # Python dependencies
│   └── Dockerfile                # Container build
└── assets/                   # Diagrams and docs
```

---

## Prerequisites

| Component | Requirement |
|-----------|-------------|
| AWS account | GPU quota approved for p5/p4d (generation) and g6e (judge) |
| NVIDIA AI Enterprise | Optional. NGC API key only needed for NIM or Blackwell nightly images, not this A100 path |
| Hugging Face | Token with access to `nvidia/cosmos3` collection |
| Python | 3.10+ recommended |
| Docker | With NVIDIA Container Toolkit |

---

## Quick start (local, mock mode)

Run the dashboard without a GPU to preview the UI and demo flow.

```bash
# Clone and enter the repo
git clone https://github.com/mhp-vishesh/Scenario-Based-Validation.git
cd Scenario-Based-Validation

# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r POC/requirements.txt

# Run the dashboard in mock mode
MOCK_MODE=true streamlit run POC/dashboard/app.py
```

Open http://localhost:8501 to explore the coverage heatmap and failure gallery with sample data.

---

## AWS setup

### 1. Request GPU quota

In the AWS console, request quota increases for:

- `p5.48xlarge` or `p4d.24xlarge` (generation node, H100/A100 80GB)
- `g6e.xlarge` or `g6e.12xlarge` (judge node, L40S)

This can take 1-3 business days. Start early.

### 2. Launch instances

Use the NVIDIA AI Enterprise AMI (or AWS Deep Learning AMI) so drivers and the container runtime are preinstalled.

```bash
# Example: launch a p4d.24xlarge generation node
aws ec2 run-instances \
  --image-id ami-XXXXXXXX \
  --instance-type p4d.24xlarge \
  --key-name your-key \
  --security-group-ids sg-XXXXXXXX \
  --subnet-id subnet-XXXXXXXX \
  --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":500,"VolumeType":"gp3"}}]'
```

### 3. Verify GPU access

```bash
nvidia-smi
docker run --rm --gpus all nvidia/cuda:12.4-base nvidia-smi
```

### 4. Authenticate

```bash
# Hugging Face (required - for Cosmos checkpoints)
huggingface-cli login

# NGC (optional - only for NIM or Blackwell nightly container images)
# docker login nvcr.io
# Username: $oauthtoken
# Password: <your NGC API key>
```

---

## Pull Cosmos models

```bash
# Clone the repos
git clone https://github.com/NVIDIA/Cosmos.git
git clone https://github.com/nvidia-cosmos/cosmos-predict2.5.git
git clone https://github.com/nvidia-cosmos/cosmos-transfer2.5.git
git clone https://github.com/nvidia-cosmos/cosmos-reason2.git

# Download checkpoints (example for Predict)
cd cosmos-predict2.5
huggingface-cli download nvidia/Cosmos-Predict2.5-12B --local-dir checkpoints/
```

Run one sample inference per model from the Cosmos Cookbook to confirm the environment before integrating.

---

## Configuration

### Scenario matrix (`config/scenario_matrix.yaml`)

Defines the axes for scenario fan-out:

```yaml
weather:
  - clear
  - rain
  - fog
  - snow

lighting:
  - day
  - dusk
  - night
  - low_sun_glare
  - tunnel_transition

actors:
  - pedestrian
  - cyclist
  - motorcycle
  - stalled_vehicle

behaviour:
  - jaywalk_cut_in
  - sudden_braking
  - occluded_emergence

geometry:
  - signalized_intersection
  - unprotected_left
  - merge
  - roundabout
```

### Judge rubric (`config/judge_rubric.yaml`)

Defines the structured verdict schema:

```yaml
verdict_schema:
  hazard_detected_in_time: bool
  action_safe: bool
  failure_category: string   # e.g. "late_detection", "wrong_action", "false_positive"
  risk_score: int            # 1-5
  rationale: string          # plain language explanation
```

---

## Running the pipeline

### 1. Generate scenarios

```bash
python scripts/generate.py \
  --seeds seeds/ \
  --matrix config/scenario_matrix.yaml \
  --output outputs/ \
  --manifest outputs/manifest.json
```

This uses Cosmos Transfer (with segmentation/depth/HD-map controls) and Cosmos Predict to generate variants.

### 2. Validate

```bash
python scripts/validate.py \
  --clips outputs/ \
  --manifest outputs/manifest.json \
  --rubric config/judge_rubric.yaml \
  --sut <path-to-system-under-test>
```

This runs the system under test on each clip, then calls Cosmos Reason to produce structured verdicts.

### 3. Launch the dashboard

```bash
streamlit run dashboard/app.py
```

### 4. Export the validation report

```bash
python scripts/export_report.py \
  --manifest outputs/manifest.json \
  --output validation_report.pdf
```

---

## Manifest schema

Every generated clip is logged for reproducibility:

```json
{
  "clip_id": "seed01_rain_night_pedestrian_jaywalk_001",
  "seed_id": "seed01",
  "scenario": {
    "weather": "rain",
    "lighting": "night",
    "actors": ["pedestrian"],
    "behaviour": "jaywalk_cut_in",
    "geometry": "signalized_intersection"
  },
  "generation": {
    "model": "cosmos-transfer2.5",
    "checkpoint": "v2.5.1",
    "prompt": "...",
    "control_inputs": ["segmentation", "depth"],
    "random_seed": 42
  },
  "validation": {
    "sut_output_path": "outputs/sut/seed01_rain_night_pedestrian_jaywalk_001.json",
    "verdict": {
      "hazard_detected_in_time": false,
      "action_safe": false,
      "failure_category": "late_detection",
      "risk_score": 4,
      "rationale": "Pedestrian entered crosswalk at frame 45. Detection triggered at frame 72. Braking initiated too late to avoid contact."
    },
    "realism_score": 0.87
  }
}
```

---

## Cost management

- Generate in short batches, snapshot outputs to S3, then stop the p5/p4d node.
- Keep only the small judge node (g6e) running between batches.
- Pre-generate all demo assets so the live walkthrough never waits on a GPU.

---

## Testing

```bash
pytest tests/ -v
```

---

## References

- [NVIDIA Cosmos](https://www.nvidia.com/en-us/ai/cosmos/)
- [Cosmos GitHub](https://github.com/NVIDIA/Cosmos)
- [Cosmos Cookbook](https://nvidia-cosmos.github.io/cosmos-cookbook/)
- [Hugging Face: nvidia/cosmos3](https://huggingface.co/collections/nvidia/cosmos3)
- [ISO 21448 (SOTIF)](https://www.iso.org/standard/77490.html)
- [ISO 26262 (Functional Safety)](https://www.iso.org/standard/68383.html)

---
