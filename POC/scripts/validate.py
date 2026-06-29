#!/usr/bin/env python3
"""Run system under test and judge validation on generated clips.

Usage:
    python scripts/validate.py --clips outputs/ --manifest outputs/manifest.json --rubric config/judge_rubric.yaml

The system under test is YOLO v8 for object detection. The judge (Cosmos Reason)
evaluates whether the SUT detected hazards correctly and in time.
"""
import argparse
import json
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from judge import Judge
from evaluator import RealistmEvaluator
from manifest import Manifest
from sut import create_sut, SystemUnderTest
from utils import (
    load_yaml,
    ensure_dir,
    get_video_frames,
    save_json,
    ProgressTracker,
    logger,
)


def parse_args():
    parser = argparse.ArgumentParser(description="Validate generated scenarios")
    parser.add_argument("--clips", required=True, help="Path to generated clips directory")
    parser.add_argument("--manifest", required=True, help="Path to manifest file")
    parser.add_argument("--rubric", required=True, help="Path to judge rubric YAML")
    parser.add_argument("--yolo-model", default="yolov8n.pt", help="YOLO model variant (n/s/m/l/x)")
    parser.add_argument("--confidence", type=float, default=0.5, help="Detection confidence threshold")
    parser.add_argument("--reason-checkpoint", help="Path to Cosmos Reason checkpoint")
    parser.add_argument("--evaluator-checkpoint", help="Path to Cosmos Evaluator checkpoint")
    parser.add_argument("--output", default="outputs/", help="Output directory for results")
    parser.add_argument("--skip-existing", action="store_true", help="Skip already validated clips")
    return parser.parse_args()


def load_sut(model: str = "yolov8n.pt", confidence: float = 0.5) -> SystemUnderTest:
    """Load the YOLO v8 system under test.
    
    Args:
        model: YOLO model variant (yolov8n/s/m/l/x.pt)
        confidence: Detection confidence threshold
        
    Returns:
        Configured SystemUnderTest with YOLO v8 detector
    """
    logger.info(f"Loading YOLO v8 SUT: model={model}, confidence={confidence}")
    return create_sut(model=model, confidence=confidence)


def main():
    args = parse_args()
    
    # Load manifest
    manifest = Manifest(args.manifest)
    logger.info(f"Loaded manifest with {len(manifest.entries)} entries")
    
    # Filter to entries needing validation
    entries_to_validate = [
        e for e in manifest.entries
        if not args.skip_existing or not e.get("validation")
    ]
    logger.info(f"Validating {len(entries_to_validate)} clips")
    
    if not entries_to_validate:
        logger.info("No clips to validate")
        return
    
    # Initialize components
    judge = Judge(
        rubric_path=args.rubric,
        checkpoint_path=args.reason_checkpoint,
    )
    evaluator = RealistmEvaluator(args.evaluator_checkpoint)
    sut = load_sut(model=args.yolo_model, confidence=args.confidence)
    
    # Ensure output directories
    output_dir = ensure_dir(args.output)
    sut_output_dir = ensure_dir(output_dir / "sut")
    
    # Process each clip
    with ProgressTracker(len(entries_to_validate), "Validating clips") as progress:
        for entry in entries_to_validate:
            clip_id = entry["clip_id"]
            
            # Find the clip file
            clips_dir = Path(args.clips) / "clips"
            clip_path = clips_dir / f"{clip_id}.mp4"
            
            if not clip_path.exists():
                # Try without clips subdirectory
                clip_path = Path(args.clips) / f"{clip_id}.mp4"
            
            # Load video frames
            if clip_path.exists():
                frames = get_video_frames(str(clip_path))
            else:
                frames = []
                logger.warning(f"Clip not found: {clip_path}, skipping frames")
            
            # Run system under test
            sut_output = sut.run(frames)
            
            # Save SUT output
            sut_output_path = sut_output_dir / f"{clip_id}.json"
            save_json(sut_output, str(sut_output_path))
            
            # Run judge
            judge_result = judge.evaluate(
                video_frames=frames,
                sut_output=sut_output,
                scenario_metadata=entry.get("scenario", {}),
                video_path=str(clip_path) if clip_path.exists() else None,
            )
            
            # Run realism evaluator
            realism_result = evaluator.score(frames)
            
            # Update manifest
            manifest.update_validation(
                clip_id=clip_id,
                verdict=judge_result["verdict"],
                realism_score=realism_result["score"],
                sut_output_path=str(sut_output_path),
            )
            
            progress.update()
    
    # Save updated manifest
    manifest.save()
    
    # Print summary
    stats = manifest.get_statistics()
    logger.info("Validation complete:")
    logger.info(f"  Total validated: {stats['validated']}")
    logger.info(f"  Failures found: {stats['failures']}")
    logger.info(f"  Pass rate: {stats['pass_rate']*100:.1f}%")
    logger.info(f"  Average realism: {stats['average_realism_score']:.3f}")
    
    if stats['failure_categories']:
        logger.info("  Failure categories:")
        for cat, count in stats['failure_categories'].items():
            logger.info(f"    - {cat}: {count}")


if __name__ == "__main__":
    main()
