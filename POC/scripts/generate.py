#!/usr/bin/env python3
"""Batch scenario generation using Cosmos Transfer and Predict.

Usage:
    python scripts/generate.py --seeds seeds/ --matrix config/scenario_matrix.yaml --output outputs/
"""
import argparse
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cosmos_wrapper import CosmosPredict, CosmosTransfer
from manifest import Manifest
from utils import (
    load_yaml,
    generate_scenario_combinations,
    ensure_dir,
    get_video_frames,
    save_video_frames,
    ProgressTracker,
    logger,
)


def parse_args():
    parser = argparse.ArgumentParser(description="Generate scenario variants")
    parser.add_argument("--seeds", required=True, help="Path to seed clips directory")
    parser.add_argument("--matrix", required=True, help="Path to scenario matrix YAML")
    parser.add_argument("--output", required=True, help="Output directory for generated clips")
    parser.add_argument("--manifest", default="outputs/manifest.json", help="Manifest file path")
    parser.add_argument("--predict-checkpoint", help="Path to Cosmos Predict checkpoint")
    parser.add_argument("--transfer-checkpoint", help="Path to Cosmos Transfer checkpoint")
    parser.add_argument("--max-scenarios", type=int, default=500, help="Max scenarios to generate")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be generated")
    return parser.parse_args()


def get_seed_clips(seeds_dir: str) -> list:
    """Find all seed clips in the directory."""
    seeds_path = Path(seeds_dir)
    clips = []
    
    for ext in ["*.mp4", "*.avi", "*.mov"]:
        clips.extend(seeds_path.glob(ext))
    
    # Also check for frame sequences (directories with images)
    for d in seeds_path.iterdir():
        if d.is_dir() and any(d.glob("*.png")) or any(d.glob("*.jpg")):
            clips.append(d)
    
    return sorted(clips)


def build_prompt(scenario: dict) -> str:
    """Build a generation prompt from scenario parameters."""
    weather_prompts = {
        "clear": "clear sunny weather",
        "rain": "heavy rain with wet roads and reflections",
        "fog": "dense fog with limited visibility",
        "snow": "snowy conditions with snow on the road",
        "wet_road": "wet road surface after rain",
    }
    
    lighting_prompts = {
        "day": "bright daylight",
        "dusk": "dusk lighting with long shadows",
        "night": "nighttime with headlights and streetlights",
        "low_sun_glare": "low sun causing glare on the windshield",
        "tunnel_transition": "transitioning from bright light into a dark tunnel",
    }
    
    actor_prompts = {
        "pedestrian": "a pedestrian",
        "cyclist": "a cyclist on a bicycle",
        "motorcycle": "a motorcycle",
        "stalled_vehicle": "a stalled vehicle blocking the lane",
        "animal": "an animal crossing the road",
    }
    
    behaviour_prompts = {
        "jaywalk_cut_in": "suddenly jaywalking across the road in front of the vehicle",
        "sudden_braking": "suddenly braking in front of the vehicle",
        "occluded_emergence": "emerging from behind a parked vehicle into the road",
        "lane_change_no_signal": "changing lanes without signaling",
        "running_red_light": "running a red light at the intersection",
    }
    
    weather = weather_prompts.get(scenario["weather"], scenario["weather"])
    lighting = lighting_prompts.get(scenario["lighting"], scenario["lighting"])
    actors = [actor_prompts.get(a, a) for a in scenario["actors"]]
    behaviour = behaviour_prompts.get(scenario["behaviour"], scenario["behaviour"])
    
    actor_str = " and ".join(actors)
    
    prompt = f"A driving scene with {weather}, {lighting}. {actor_str} is {behaviour}."
    return prompt


def main():
    args = parse_args()
    
    # Load configuration
    matrix = load_yaml(args.matrix)
    logger.info(f"Loaded scenario matrix from {args.matrix}")
    
    # Find seed clips
    seed_clips = get_seed_clips(args.seeds)
    if not seed_clips:
        logger.error(f"No seed clips found in {args.seeds}")
        sys.exit(1)
    logger.info(f"Found {len(seed_clips)} seed clips")
    
    # Generate scenario combinations
    scenarios = list(generate_scenario_combinations(
        matrix,
        strategy=matrix.get("sampling", {}).get("strategy", "random"),
        max_scenarios=args.max_scenarios,
    ))
    logger.info(f"Generated {len(scenarios)} scenario combinations")
    
    if args.dry_run:
        logger.info("Dry run - would generate:")
        for i, scenario in enumerate(scenarios[:10]):
            prompt = build_prompt(scenario)
            logger.info(f"  {i+1}. {scenario} -> {prompt[:80]}...")
        if len(scenarios) > 10:
            logger.info(f"  ... and {len(scenarios) - 10} more")
        return
    
    # Initialize models
    predict = CosmosPredict(args.predict_checkpoint)
    transfer = CosmosTransfer(args.transfer_checkpoint)
    
    # Initialize manifest
    manifest = Manifest(args.manifest)
    
    # Ensure output directory
    output_dir = ensure_dir(args.output)
    clips_dir = ensure_dir(output_dir / "clips")
    
    # Generation settings
    gen_config = matrix.get("generation", {})
    clips_per_combo = gen_config.get("clips_per_combination", 1)
    video_length = gen_config.get("video_length_seconds", 5)
    fps = gen_config.get("fps", 30)
    num_frames = video_length * fps
    
    total_clips = len(seed_clips) * len(scenarios) * clips_per_combo
    logger.info(f"Generating {total_clips} clips total")
    
    # Generate
    with ProgressTracker(total_clips, "Generating clips") as progress:
        clip_num = 0
        
        for seed_path in seed_clips:
            seed_id = seed_path.stem if seed_path.is_file() else seed_path.name
            
            # Load seed frames
            if seed_path.is_file():
                seed_frames = get_video_frames(str(seed_path))
            else:
                # Frame sequence directory
                seed_frames = []  # TODO: load frame sequence
            
            for scenario in scenarios:
                prompt = build_prompt(scenario)
                
                for seq in range(clips_per_combo):
                    clip_id = manifest.generate_clip_id(seed_id, scenario, clip_num)
                    seed = gen_config.get("random_seed_base", 42) + clip_num
                    
                    # Use Transfer for controlled generation
                    control_inputs = {
                        ctrl: None  # Placeholder for actual control inputs
                        for ctrl in matrix.get("control_inputs", ["segmentation"])
                    }
                    
                    result = transfer.generate(
                        input_frames=seed_frames,
                        control_inputs=control_inputs,
                        prompt=prompt,
                        num_frames=num_frames,
                        seed=seed,
                    )
                    
                    # Save generated clip
                    clip_path = clips_dir / f"{clip_id}.mp4"
                    if result.get("frames"):
                        save_video_frames(result["frames"], str(clip_path), fps=fps)
                    
                    # Add to manifest
                    manifest.add_entry(
                        clip_id=clip_id,
                        seed_id=seed_id,
                        scenario=scenario,
                        generation={
                            "model": result.get("metadata", {}).get("model", "cosmos-transfer2.5"),
                            "checkpoint": args.transfer_checkpoint,
                            "prompt": prompt,
                            "control_inputs": list(control_inputs.keys()),
                            "random_seed": seed,
                            "num_frames": num_frames,
                        },
                    )
                    
                    clip_num += 1
                    progress.update()
    
    # Save manifest
    manifest.save()
    logger.info(f"Saved manifest to {args.manifest}")
    logger.info(f"Generation complete: {clip_num} clips generated")


if __name__ == "__main__":
    main()
