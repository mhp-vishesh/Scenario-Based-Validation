"""Thin wrappers around Cosmos model inference.

Real inference paths:
  - CosmosPredict / CosmosTransfer call the official Cosmos CLI
    (examples/inference.py) as a subprocess inside the cloned model repo,
    then read the produced mp4 back into frames.
  - CosmosReason runs the Cosmos-Reason2-8B vision-language model directly
    through transformers (Qwen3-VL).

Configuration is via environment variables:
  COSMOS_PREDICT_REPO     path to the Cosmos-Predict2.5 checkout
  COSMOS_PREDICT_MODEL    model key passed to --model (default 14B/post-trained)
  COSMOS_PREDICT_PYTHON   interpreter for the Predict repo (default: python)
  COSMOS_TRANSFER_REPO    path to the Cosmos-Transfer2.5 checkout
  COSMOS_TRANSFER_MODEL   model key passed to --model (optional)
  COSMOS_TRANSFER_PYTHON  interpreter for the Transfer repo (default: python)
  COSMOS_TRANSFER_CONTROL default control branch: edge|depth|vis|seg (default edge)
  COSMOS_REASON_CHECKPOINT  HF id or local path (default nvidia/Cosmos-Reason2-8B)
"""
import os
import json
import glob
import shlex
import tempfile
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, List

# Directory of the cloned Cosmos model repos (POC/cosmos/...).
_COSMOS_ROOT = Path(__file__).resolve().parents[1] / "cosmos"


def _python_cmd(env_var: str) -> List[str]:
    """Resolve the interpreter command for a Cosmos repo.

    Allows values like "python", "uv run python" or an absolute venv path.
    """
    raw = os.environ.get(env_var) or os.environ.get("COSMOS_PYTHON") or "python"
    return shlex.split(raw)


def _write_temp_video(frames: List[Any], fps: int) -> str:
    """Encode in-memory frames to a temporary mp4 and return its path."""
    try:
        from utils import save_video_frames
    except ImportError:
        from .utils import save_video_frames
    fd, path = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)
    save_video_frames(frames, path, fps=fps)
    return path


def _read_video_frames(path: str) -> List[Any]:
    """Decode an mp4 into a list of frames (PIL Images)."""
    try:
        from utils import get_video_frames
    except ImportError:
        from .utils import get_video_frames
    return get_video_frames(path)


def _run_cosmos_cli(repo_dir: str, python_cmd: List[str], cli_args: List[str], tag: str):
    """Run examples/inference.py inside a Cosmos repo as a subprocess."""
    if not os.path.isdir(repo_dir):
        raise RuntimeError(
            f"{tag}: Cosmos repo not found at {repo_dir}. "
            f"Set the matching COSMOS_*_REPO env var or pull the model submodule."
        )
    cmd = list(python_cmd) + cli_args
    print(f"[{tag}] running: {' '.join(shlex.quote(c) for c in cmd)} (cwd={repo_dir})")
    result = subprocess.run(cmd, cwd=repo_dir, capture_output=True, text=True)
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "")[-2000:]
        raise RuntimeError(f"{tag} inference failed (exit {result.returncode}):\n{tail}")
    return result


def _newest_mp4(out_dir: str) -> str:
    """Return the most recently written mp4 under out_dir."""
    vids = glob.glob(os.path.join(out_dir, "**", "*.mp4"), recursive=True)
    if not vids:
        raise RuntimeError(f"No output video was produced in {out_dir}")
    return max(vids, key=os.path.getmtime)


def _extract_answer(text: str) -> str:
    """Pull the answer portion out of a Cosmos-Reason <think>/<answer> response.

    Falls back to the text after </think>, then to the full text.
    """
    import re
    match = re.search(r"<answer>\s*(.*?)\s*</answer>", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    if "</think>" in text:
        return text.split("</think>", 1)[1].strip()
    return text.strip()


class CosmosPredict:
    """Wrapper for Cosmos Predict (world future generation)."""

    def __init__(self, checkpoint_path: Optional[str] = None):
        self.checkpoint_path = checkpoint_path
        self.model = None
        self.repo_dir = os.environ.get(
            "COSMOS_PREDICT_REPO", str(_COSMOS_ROOT / "Cosmos-Predict2.5")
        )
        self.model_key = os.environ.get("COSMOS_PREDICT_MODEL", "14B/post-trained")
        self.python_cmd = _python_cmd("COSMOS_PREDICT_PYTHON")

        self._load_model()

    def _load_model(self):
        """Validate that the Cosmos Predict checkout is present.

        The model weights are loaded by the CLI subprocess per run, so there is
        no in-process model to hold here. We only check the repo exists.
        """
        if not os.path.isdir(self.repo_dir):
            raise RuntimeError(
                f"Cosmos Predict repo not found at {self.repo_dir}. "
                f"Set COSMOS_PREDICT_REPO or pull the submodule."
            )
        print(f"[CosmosPredict] Using repo {self.repo_dir} (model={self.model_key})")

    def generate(
        self,
        input_frames: List[Any],
        prompt: str,
        num_frames: int = 150,
        guidance_scale: float = 7.0,
        seed: int = 42,
        inference_type: Optional[str] = None,
        input_video_path: Optional[str] = None,
        num_steps: int = 35,
        negative_prompt: Optional[str] = None,
        input_fps: int = 30,
        output_dir: Optional[str] = None,
        name: str = "scenario",
    ) -> Dict[str, Any]:
        """Generate future frames from input context.

        Args:
            input_frames: List of input frames (PIL Images or numpy arrays)
            prompt: Text prompt describing the desired scenario
            num_frames: Number of frames to generate (maps to num_output_frames)
            guidance_scale: Classifier-free guidance scale (maps to guidance)
            seed: Random seed for reproducibility
            inference_type: text2world|image2world|video2world. Inferred from
                the presence of input frames when not given.
            input_video_path: Optional path to an existing conditioning video.
            num_steps: Diffusion steps.
            negative_prompt: Optional negative prompt.
            input_fps: FPS used when encoding input_frames to a temp video.
            output_dir: Where the CLI writes output (a temp dir by default).
            name: Sample name written into the input spec.

        Returns:
            Dict with 'frames', 'video_path' and 'metadata'.
        """
        if inference_type is None:
            inference_type = "video2world" if (input_video_path or input_frames) else "text2world"

        tmp_input = None
        spec_path = None
        out_dir = output_dir or tempfile.mkdtemp(prefix="cosmos_predict_")
        try:
            spec: Dict[str, Any] = {
                "name": name,
                "inference_type": inference_type,
                "prompt": prompt,
                "num_output_frames": int(num_frames),
                "num_steps": int(num_steps),
                "seed": int(seed),
                "guidance": max(0, min(7, int(round(guidance_scale)))),
            }
            if negative_prompt:
                spec["negative_prompt"] = negative_prompt

            if inference_type != "text2world":
                if not input_video_path and input_frames:
                    tmp_input = _write_temp_video(input_frames, input_fps)
                    input_video_path = tmp_input
                if input_video_path:
                    spec["input_path"] = os.path.abspath(input_video_path)

            fd, spec_path = tempfile.mkstemp(suffix=".json")
            with os.fdopen(fd, "w") as f:
                json.dump(spec, f)

            cli = ["examples/inference.py", "-i", spec_path, "-o", out_dir]
            if self.model_key:
                cli += ["--model", self.model_key]
            # The guardrail repo (nvidia/Cosmos-Guardrail1) is gated and not
            # needed for this POC, so always skip it. Leaving it enabled forces
            # a download that fails with an access-denied error on accounts
            # without approval.
            cli += ["--disable-guardrails"]
            if os.environ.get("COSMOS_PREDICT_LOWVRAM", "0") == "1":
                # Fit the 2B pipeline on a 24GB GPU: load components to CPU and
                # stream each to the GPU only for its own pass (text encoder,
                # diffusion model, tokenizer/VAE).
                # --offload-diffusion-model also stops the loader from forcing
                # every component onto the GPU at construction time.
                cli += [
                    "--offload-diffusion-model",
                    "--offload-text-encoder",
                    "--offload-tokenizer",
                ]
            extra = os.environ.get("COSMOS_PREDICT_EXTRA_ARGS", "").strip()
            if extra:
                cli += shlex.split(extra)

            _run_cosmos_cli(self.repo_dir, self.python_cmd, cli, "CosmosPredict")
            out_path = _newest_mp4(out_dir)
            frames = _read_video_frames(out_path)
            return {
                "frames": frames,
                "video_path": out_path,
                "metadata": {
                    "model": self.model_key or "cosmos-predict2.5",
                    "prompt": prompt,
                    "inference_type": inference_type,
                    "num_frames": len(frames),
                    "seed": seed,
                },
            }
        finally:
            for p in (tmp_input, spec_path):
                if p and os.path.exists(p):
                    os.remove(p)


class CosmosTransfer:
    """Wrapper for Cosmos Transfer (conditional generation with control inputs)."""

    def __init__(self, checkpoint_path: Optional[str] = None):
        self.checkpoint_path = checkpoint_path
        self.model = None
        self.repo_dir = os.environ.get(
            "COSMOS_TRANSFER_REPO", str(_COSMOS_ROOT / "Cosmos-Transfer2.5")
        )
        self.model_key = os.environ.get("COSMOS_TRANSFER_MODEL")  # optional
        self.control_type = os.environ.get("COSMOS_TRANSFER_CONTROL", "edge")
        self.python_cmd = _python_cmd("COSMOS_TRANSFER_PYTHON")

        self._load_model()

    def _load_model(self):
        """Validate that the Cosmos Transfer checkout is present."""
        if not os.path.isdir(self.repo_dir):
            raise RuntimeError(
                f"Cosmos Transfer repo not found at {self.repo_dir}. "
                f"Set COSMOS_TRANSFER_REPO or pull the submodule."
            )
        print(f"[CosmosTransfer] Using repo {self.repo_dir} (control={self.control_type})")

    def generate(
        self,
        input_frames: List[Any],
        control_inputs: Dict[str, Any],
        prompt: str,
        num_frames: int = 150,
        guidance_scale: float = 7.5,
        control_scale: float = 1.0,
        seed: int = 42,
        input_video_path: Optional[str] = None,
        control_type: Optional[str] = None,
        num_steps: int = 35,
        input_fps: int = 30,
        output_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate video conditioned on control inputs.

        Args:
            input_frames: List of input frames used as the conditioning video.
            control_inputs: Control signals. When it contains a single key
                matching a control branch (edge/depth/vis/seg) that branch is
                used; otherwise control_type / COSMOS_TRANSFER_CONTROL applies.
            prompt: Text prompt for the scenario.
            num_frames: Number of frames to generate (maps to num_output_frames).
            guidance_scale: Text guidance scale (maps to guidance).
            control_scale: Control input weight (passed through metadata only).
            seed: Random seed.
            input_video_path: Optional path to an existing conditioning video.
            control_type: Override the control branch (edge|depth|vis|seg).
            num_steps: Diffusion steps.
            input_fps: FPS used when encoding input_frames to a temp video.
            output_dir: Where the CLI writes output (a temp dir by default).

        Returns:
            Dict with 'frames', 'video_path' and 'metadata'.

        Note:
            The Cosmos-Transfer2.5 input-spec keys and the per-control hint
            videos (segmentation/depth maps derived from the seed clip) are
            finalized against the cloned repo on the GPU node. This wrapper
            wires the real CLI, control branch and output handling; control
            preprocessing is added when the Transfer model is exercised.
        """
        # Pick the control branch from the supplied control inputs when possible.
        branch = control_type or self.control_type
        valid = {"edge", "depth", "vis", "seg"}
        if control_inputs:
            keys = [k for k in control_inputs if k in valid]
            if len(keys) == 1:
                branch = keys[0]
        if branch not in valid:
            branch = "edge"

        tmp_input = None
        spec_path = None
        out_dir = output_dir or tempfile.mkdtemp(prefix="cosmos_transfer_")
        try:
            if not input_video_path and input_frames:
                tmp_input = _write_temp_video(input_frames, input_fps)
                input_video_path = tmp_input
            if not input_video_path:
                raise ValueError(
                    "CosmosTransfer requires a conditioning video "
                    "(input_video_path or input_frames)."
                )

            spec: Dict[str, Any] = {
                "prompt": prompt,
                "input_video": os.path.abspath(input_video_path),
                "num_output_frames": int(num_frames),
                "num_steps": int(num_steps),
                "seed": int(seed),
                "guidance": float(guidance_scale),
            }
            fd, spec_path = tempfile.mkstemp(suffix=".json")
            with os.fdopen(fd, "w") as f:
                json.dump(spec, f)

            cli = ["examples/inference.py", "-i", spec_path, "-o", out_dir]
            if self.model_key:
                cli += ["--model", self.model_key]
            cli += [f"control:{branch}"]

            _run_cosmos_cli(self.repo_dir, self.python_cmd, cli, "CosmosTransfer")
            out_path = _newest_mp4(out_dir)
            frames = _read_video_frames(out_path)
            return {
                "frames": frames,
                "video_path": out_path,
                "metadata": {
                    "model": self.model_key or "cosmos-transfer2.5",
                    "prompt": prompt,
                    "control": branch,
                    "control_scale": control_scale,
                    "num_frames": len(frames),
                    "seed": seed,
                },
            }
        finally:
            for p in (tmp_input, spec_path):
                if p and os.path.exists(p):
                    os.remove(p)


class CosmosReason:
    """Wrapper for Cosmos Reason (vision-language reasoning)."""

    def __init__(self, checkpoint_path: Optional[str] = None):
        self.model_name = (
            checkpoint_path
            or os.environ.get("COSMOS_REASON_CHECKPOINT")
            or "nvidia/Cosmos-Reason2-8B"
        )
        self.checkpoint_path = self.model_name
        self.model = None
        self.processor = None
        self._torch = None

        self._load_model()

    def _load_model(self):
        """Load the Cosmos-Reason2 vision-language model via transformers."""
        try:
            import torch
            from transformers import AutoProcessor, Qwen3VLForConditionalGeneration
        except ImportError as e:
            raise RuntimeError(
                "Cosmos Reason needs torch + a transformers build with Qwen3-VL "
                "support. Install them on the GPU node per the model card."
            ) from e

        print(f"[CosmosReason] Loading {self.model_name}")
        self._torch = torch
        self.model = Qwen3VLForConditionalGeneration.from_pretrained(
            self.model_name,
            dtype=torch.bfloat16,
            device_map="auto",
            attn_implementation="sdpa",
        )
        self.processor = AutoProcessor.from_pretrained(self.model_name)

    def analyze(
        self,
        video_frames: Optional[List[Any]] = None,
        system_prompt: str = "",
        user_prompt: str = "",
        video_path: Optional[str] = None,
        fps: int = 4,
        max_tokens: int = 4096,
    ) -> Dict[str, Any]:
        """Analyze a video clip and produce structured reasoning.

        Args:
            video_frames: Frames to analyze (used only if video_path is absent).
            system_prompt: System instructions for the judge.
            user_prompt: Specific question or analysis request.
            video_path: Path to the clip. Preferred over video_frames; the model
                samples the file directly at the given fps.
            fps: Sampling rate fed to the processor.
            max_tokens: Maximum response tokens.

        Returns:
            Dict with 'response' (the answer text) and 'metadata'.
        """
        if self.model is None:
            self._load_model()

        tmp_video = None
        try:
            if not video_path:
                if not video_frames:
                    raise ValueError(
                        "CosmosReason.analyze needs either video_path or video_frames."
                    )
                tmp_video = _write_temp_video(video_frames, fps)
                video_path = tmp_video
            abs_path = os.path.abspath(video_path)

            sys_text = (system_prompt or "You are a careful driving-safety analyst.").strip()
            sys_text += (
                "\n\nAnswer the question in the following format: <think>\n"
                "your reasoning process here\n</think>\n\n<answer>\n"
                "your answer here\n</answer>."
            )
            messages = [
                {"role": "system", "content": [{"type": "text", "text": sys_text}]},
                {
                    "role": "user",
                    "content": [
                        {"type": "video", "video": abs_path, "fps": fps},
                        {"type": "text", "text": user_prompt},
                    ],
                },
            ]

            inputs = self.processor.apply_chat_template(
                messages,
                tokenize=True,
                add_generation_prompt=True,
                return_dict=True,
                return_tensors="pt",
                fps=fps,
            ).to(self.model.device)

            with self._torch.inference_mode():
                generated = self.model.generate(**inputs, max_new_tokens=max_tokens)

            trimmed = [
                out[len(inp):] for inp, out in zip(inputs.input_ids, generated)
            ]
            text = self.processor.batch_decode(
                trimmed,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False,
            )[0]

            return {
                "response": _extract_answer(text),
                "metadata": {
                    "model": self.model_name,
                    "raw_response": text,
                    "fps": fps,
                    "max_tokens": max_tokens,
                },
            }
        finally:
            if tmp_video and os.path.exists(tmp_video):
                os.remove(tmp_video)
