#!/usr/bin/env python3
"""End-to-end demo: one real seed video -> 3 generated clips -> YOLO -> judge.

This script runs the full pipeline on a single seed and writes a manifest the
Streamlit dashboard can read. It runs on the GPU node:
  - Generation uses Cosmos Predict (video2world) on the seed.
  - YOLO runs for real on each generated clip.
  - The Cosmos Reason judge runs for real on each clip.

Usage:
    python scripts/run_demo.py --seed seeds/<file>.mp4 --output outputs/
"""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from manifest import Manifest
from judge import Judge
from evaluator import RealistmEvaluator
from utils import ensure_dir, save_video_frames, logger


def save_browser_video(frames, out_path, fps):
    """Write an H.264 (yuv420p) mp4 that browsers can play in the dashboard.

    Falls back to the OpenCV writer if imageio is unavailable.
    """
    try:
        import numpy as np
        import imageio
        from PIL import Image

        arrays = []
        for f in frames:
            arr = np.array(f) if isinstance(f, Image.Image) else np.asarray(f)
            arrays.append(arr)
        writer = imageio.get_writer(
            str(out_path),
            fps=fps,
            codec="libx264",
            format="FFMPEG",
            pixelformat="yuv420p",
            macro_block_size=None,
            output_params=["-movflags", "+faststart"],
        )
        for arr in arrays:
            writer.append_data(arr)
        writer.close()
    except Exception as exc:  # pragma: no cover - fallback path
        logger.warning("imageio H.264 write failed (%s); using OpenCV writer", exc)
        save_video_frames(frames, str(out_path), fps=fps)


# Three scenario variations generated from the single seed. The "transform"
# tag drives the local colour treatment; the prompt drives Cosmos on the GPU.
SCENARIOS = [
    {
        "weather": "fog",
        "lighting": "dusk",
        "actors": ["pedestrian"],
        "behaviour": "occluded_emergence",
        "geometry": "highway_exit",
        "transform": "fog",
    },
    {
        "weather": "rain",
        "lighting": "night",
        "actors": ["stalled_vehicle"],
        "behaviour": "sudden_braking",
        "geometry": "merge",
        "transform": "night_rain",
    },
    {
        "weather": "clear",
        "lighting": "low_sun_glare",
        "actors": ["cyclist"],
        "behaviour": "jaywalk_cut_in",
        "geometry": "merge",
        "transform": "glare",
    },
]


def parse_args():
    p = argparse.ArgumentParser(description="One-seed end-to-end demo")
    p.add_argument("--seed", required=True, help="Path to the seed video")
    p.add_argument("--output", default="outputs/", help="Output directory")
    p.add_argument("--rubric", default=str(ROOT / "config" / "judge_rubric.yaml"))
    p.add_argument("--clip-seconds", type=float, default=5.0)
    p.add_argument("--cond-seconds", type=float, default=1.0,
                   help="Seconds of seed used as Cosmos conditioning (GPU path)")
    p.add_argument("--max-gen-frames", type=int, default=77,
                   help="Cap on frames generated per clip (Cosmos native capacity)")
    p.add_argument("--fps", type=int, default=20)
    p.add_argument("--width", type=int, default=640)
    p.add_argument("--yolo-model", default="yolov8n.pt")
    p.add_argument("--confidence", type=float, default=0.35)
    return p.parse_args()


def build_prompt(scenario: dict) -> str:
    weather = {
        "clear": "clear weather",
        "rain": "heavy rain with wet reflective road",
        "fog": "dense fog with limited visibility",
        "snow": "snow on the road",
    }.get(scenario["weather"], scenario["weather"])
    lighting = {
        "day": "daylight",
        "dusk": "dusk with long shadows",
        "night": "night with headlights and streetlights",
        "low_sun_glare": "low sun causing glare",
    }.get(scenario["lighting"], scenario["lighting"])
    actor = {
        "pedestrian": "a pedestrian",
        "cyclist": "a cyclist",
        "stalled_vehicle": "a stalled vehicle blocking the lane",
    }.get(scenario["actors"][0], scenario["actors"][0])
    behaviour = {
        "occluded_emergence": "emerging from behind a vehicle into the lane",
        "sudden_braking": "forcing a sudden brake ahead",
        "jaywalk_cut_in": "cutting across the road in front of the car",
    }.get(scenario["behaviour"], scenario["behaviour"])
    return (
        f"A motorway driving scene in {weather}, {lighting}. "
        f"{actor} is {behaviour}."
    )


def extract_seed_window(seed_path, start_frac, seconds, fps, width, out_path):
    """Cut a short raw window from the seed to use as Cosmos conditioning.

    No colour transform here. The window anchors the scene; the prompt drives
    the scenario. Returns the saved clip path.
    """
    import cv2
    from PIL import Image

    cap = cv2.VideoCapture(str(seed_path))
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    w = cap.get(cv2.CAP_PROP_FRAME_WIDTH) or width
    h = cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or width
    scale = width / float(w)
    out_w, out_h = width, int(round(h * scale))

    start = int(total * start_frac)
    step = max(1, int(round(src_fps / fps)))
    n_out = int(seconds * fps)

    cap.set(cv2.CAP_PROP_POS_FRAMES, start)
    frames = []
    idx = 0
    while len(frames) < n_out:
        ret, frame = cap.read()
        if not ret:
            break
        if idx % step == 0:
            frame = cv2.resize(frame, (out_w, out_h))
            frames.append(Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
        idx += 1
    cap.release()

    save_browser_video(frames, str(out_path), fps=fps)
    return out_path


def generate_clip(seed_path, start_frac, scenario, args, out_path):
    """Produce one generated clip with Cosmos Predict on the GPU."""
    prompt = build_prompt(scenario)
    num_frames = int(args.clip_seconds * args.fps)

    # Cosmos Predict video2world conditioned on a short seed window.
    from cosmos_wrapper import CosmosPredict
    from utils import get_video_frames

    cond_path = out_path.parent / f"{out_path.stem}_cond.mp4"
    extract_seed_window(
        seed_path, start_frac, args.cond_seconds, args.fps, args.width, cond_path
    )

    # Cosmos Predict2.5 generates up to its native temporal capacity in one pass.
    gen_frames = min(num_frames, args.max_gen_frames)
    num_steps = int(os.environ.get("COSMOS_PREDICT_NUM_STEPS", "35"))
    predict = CosmosPredict()
    result = predict.generate(
        input_frames=None,
        input_video_path=str(cond_path),
        inference_type="video2world",
        prompt=prompt,
        num_frames=gen_frames,
        num_steps=num_steps,
        input_fps=args.fps,
        seed=42,
    )
    frames = result.get("frames") or []
    if frames:
        save_browser_video(frames, str(out_path), fps=args.fps)
    else:
        frames = get_video_frames(str(out_path))
    return frames, result.get("metadata", {})


def load_sut(args):
    """Build the YOLO SUT."""
    import sut as sut_mod

    sut = sut_mod.create_sut(model=args.yolo_model, confidence=args.confidence)
    real = getattr(sut.detector, "model", None) is not None
    logger.info(f"YOLO SUT ready (real_model={real})")
    return sut, real


def annotate_keyframe(sut, frames, out_path):
    """Run YOLO on a representative frame and save an annotated image."""
    model = getattr(sut.detector, "model", None)
    if model is None or not frames:
        return None
    try:
        import cv2
        import numpy as np

        mid = frames[len(frames) // 2]
        arr = np.array(mid)  # RGB
        res = model.predict(arr[:, :, ::-1], conf=sut.detector.confidence, verbose=False)
        plotted = res[0].plot()  # BGR with boxes
        cv2.imwrite(str(out_path), plotted)
        return str(out_path)
    except Exception as e:  # pragma: no cover - visual nicety only
        logger.warning(f"keyframe annotation failed: {e}")
        return None


def summarize_sut(sut_output):
    """Compact YOLO summary for the manifest/dashboard."""
    classes = {}
    for fr in sut_output.get("detections", []):
        for d in fr.get("detections", []):
            classes[d["class"]] = classes.get(d["class"], 0) + 1
    return {
        "action": sut_output.get("action"),
        "detection_frame": sut_output.get("detection_frame"),
        "total_hazards": sut_output.get("total_hazards"),
        "num_frames": sut_output.get("num_frames"),
        "class_counts": classes,
        "model": sut_output.get("model"),
    }


def main():
    args = parse_args()
    seed_path = Path(args.seed)
    if not seed_path.exists():
        logger.error(f"Seed not found: {seed_path}")
        sys.exit(1)

    out_dir = ensure_dir(args.output)
    clips_dir = ensure_dir(out_dir / "clips")
    sut_dir = ensure_dir(out_dir / "sut")

    logger.info(f"Seed: {seed_path.name}")

    import json

    evaluator = RealistmEvaluator()
    sut, _ = load_sut(args)

    manifest = Manifest(str(out_dir / "manifest.json"))
    manifest.entries = []  # fresh run

    start_fracs = [0.20, 0.50, 0.78]
    seed_id = seed_path.stem

    # Pass 1: generate every clip and run YOLO. The Cosmos Reason judge is NOT
    # loaded yet, so each generation subprocess has the whole GPU. A 24GB A10G
    # cannot hold the 8B judge and the generation model at the same time.
    pending = []
    for i, scenario in enumerate(SCENARIOS):
        clip_id = manifest.generate_clip_id(seed_id, scenario, i)
        clip_path = clips_dir / f"{clip_id}.mp4"

        if os.environ.get("SBV_REUSE_CLIPS") == "1" and clip_path.exists():
            from utils import get_video_frames
            frames = get_video_frames(str(clip_path))
            gen_meta = {
                "model": os.environ.get("COSMOS_PREDICT_MODEL_KEY", "cosmos-predict2.5"),
                "prompt": build_prompt(scenario),
                "num_frames": len(frames),
                "reused": True,
            }
            logger.info(f"[{i+1}/3] reusing existing clip {clip_id} ({len(frames)} frames)")
        else:
            logger.info(f"[{i+1}/3] generating {clip_id}")
            frames, gen_meta = generate_clip(
                seed_path, start_fracs[i], scenario, args, clip_path
            )

        # YOLO on a strided subset for speed; full clip stays on disk.
        stride = max(1, len(frames) // 60)
        sub = frames[::stride]
        sut_output = sut.run(sub)
        with open(sut_dir / f"{clip_id}.json", "w") as f:
            json.dump(sut_output, f, default=str)

        annotated = annotate_keyframe(sut, frames, sut_dir / f"{clip_id}_yolo.jpg")
        realism = evaluator.score(sub)

        pending.append({
            "clip_id": clip_id,
            "scenario": scenario,
            "clip_path": clip_path,
            "frames_sub": sub,
            "sut_output": sut_output,
            "gen_meta": gen_meta,
            "annotated": annotated,
            "realism": realism,
        })

    # Pass 2: now that all generation subprocesses have exited and freed the GPU,
    # load the judge once and evaluate every clip.
    logger.info("Generation complete. Loading the judge for evaluation...")
    judge = Judge(rubric_path=args.rubric)
    for p in pending:
        scenario = p["scenario"]
        clip_path = p["clip_path"]
        annotated = p["annotated"]
        judge_result = judge.evaluate(
            video_frames=p["frames_sub"],
            sut_output=p["sut_output"],
            scenario_metadata=scenario,
            video_path=str(clip_path) if clip_path.exists() else None,
        )

        manifest.add_entry(
            clip_id=p["clip_id"],
            seed_id=seed_id,
            scenario={k: v for k, v in scenario.items() if k != "transform"},
            generation={**p["gen_meta"], "prompt": build_prompt(scenario)},
            validation={
                "verdict": judge_result["verdict"],
                "realism_score": p["realism"].get("score"),
                "clip_path": str(clip_path.relative_to(out_dir)) if clip_path.exists() else None,
                "yolo_keyframe": str(Path(annotated).relative_to(out_dir)) if annotated else None,
                "sut_summary": summarize_sut(p["sut_output"]),
                "model_metadata": judge_result.get("model_metadata", {}),
            },
        )

    manifest.save()
    logger.info(f"Done. Manifest: {out_dir / 'manifest.json'}")
    logger.info(f"Clips: {clips_dir}")


if __name__ == "__main__":
    main()
