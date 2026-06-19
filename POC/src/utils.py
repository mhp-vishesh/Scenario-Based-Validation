"""Shared utilities for the Scenario-Based Validation POC."""
import os
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Iterator
from itertools import product

import yaml

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("sbv")


def load_yaml(path: str) -> Dict[str, Any]:
    """Load a YAML configuration file."""
    with open(path) as f:
        return yaml.safe_load(f)


def save_json(data: Any, path: str, indent: int = 2):
    """Save data to a JSON file."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=indent, default=str)


def load_json(path: str) -> Any:
    """Load data from a JSON file."""
    with open(path) as f:
        return json.load(f)


def generate_scenario_combinations(
    matrix: Dict[str, List[str]],
    strategy: str = "full",
    max_scenarios: int = 500,
    seed: int = 42,
) -> Iterator[Dict[str, Any]]:
    """Generate scenario combinations from the scenario matrix.
    
    Args:
        matrix: Dict with axes (weather, lighting, actors, etc.)
        strategy: 'full' for all combinations, 'random' for sampling
        max_scenarios: Maximum scenarios when using random sampling
        seed: Random seed for reproducible sampling
        
    Yields:
        Scenario dicts with one value per axis
    """
    # Extract axes
    axes = {
        "weather": matrix.get("weather", ["clear"]),
        "lighting": matrix.get("lighting", ["day"]),
        "actors": matrix.get("actors", ["pedestrian"]),
        "behaviour": matrix.get("behaviour", ["jaywalk_cut_in"]),
        "geometry": matrix.get("geometry", ["signalized_intersection"]),
    }
    
    # Generate all combinations
    keys = list(axes.keys())
    values = [axes[k] for k in keys]
    all_combinations = list(product(*values))
    
    logger.info(f"Total possible combinations: {len(all_combinations)}")
    
    if strategy == "random" and len(all_combinations) > max_scenarios:
        import random
        random.seed(seed)
        selected = random.sample(all_combinations, max_scenarios)
        logger.info(f"Randomly sampled {max_scenarios} scenarios")
    else:
        selected = all_combinations
    
    for combo in selected:
        scenario = dict(zip(keys, combo))
        # Actors should be a list
        scenario["actors"] = [scenario["actors"]]
        yield scenario


def ensure_dir(path: str) -> Path:
    """Ensure a directory exists and return its Path."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_video_frames(video_path: str) -> List[Any]:
    """Load video frames from a file.
    
    Args:
        video_path: Path to video file (mp4, avi, etc.)
        
    Returns:
        List of frames (PIL Images or numpy arrays)
    """
    try:
        import cv2
        from PIL import Image
        
        frames = []
        cap = cv2.VideoCapture(video_path)
        
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            # Convert BGR to RGB
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frames.append(Image.fromarray(frame_rgb))
        
        cap.release()
        return frames
    except ImportError:
        logger.warning("OpenCV not installed, returning empty frames")
        return []


def save_video_frames(frames: List[Any], output_path: str, fps: int = 30):
    """Save frames as a video file.
    
    Args:
        frames: List of frames (PIL Images or numpy arrays)
        output_path: Output video path
        fps: Frames per second
    """
    try:
        import cv2
        import numpy as np
        
        if not frames:
            logger.warning("No frames to save")
            return
        
        # Get dimensions from first frame
        first = frames[0]
        if hasattr(first, 'size'):  # PIL Image
            width, height = first.size
        else:  # numpy array
            height, width = first.shape[:2]
        
        # Create video writer
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
        
        for frame in frames:
            if hasattr(frame, 'convert'):  # PIL Image
                frame = np.array(frame)
            # Convert RGB to BGR
            frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            out.write(frame_bgr)
        
        out.release()
        logger.info(f"Saved video: {output_path}")
    except ImportError:
        logger.warning("OpenCV not installed, cannot save video")


class ProgressTracker:
    """Simple progress tracker with optional callback."""
    
    def __init__(self, total: int, description: str = "Processing"):
        self.total = total
        self.current = 0
        self.description = description
    
    def update(self, n: int = 1):
        """Update progress."""
        self.current += n
        pct = 100 * self.current / self.total if self.total else 0
        logger.info(f"{self.description}: {self.current}/{self.total} ({pct:.1f}%)")
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        pass
