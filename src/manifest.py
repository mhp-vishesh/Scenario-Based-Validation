"""Manifest management for reproducibility and auditing."""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import hashlib


class Manifest:
    """Manage the run manifest for reproducibility and auditing."""
    
    def __init__(self, path: str = "outputs/manifest.json"):
        self.path = Path(path)
        self.entries: List[Dict[str, Any]] = []
        self._load()
    
    def _load(self):
        """Load existing manifest if it exists."""
        if self.path.exists():
            with open(self.path) as f:
                data = json.load(f)
                if isinstance(data, list):
                    self.entries = data
                elif isinstance(data, dict) and "entries" in data:
                    self.entries = data["entries"]
    
    def save(self):
        """Save the manifest to disk."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w") as f:
            json.dump(self.entries, f, indent=2, default=str)
    
    def add_entry(
        self,
        clip_id: str,
        seed_id: str,
        scenario: Dict[str, Any],
        generation: Dict[str, Any],
        validation: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Add a new entry to the manifest.
        
        Args:
            clip_id: Unique identifier for the generated clip
            seed_id: ID of the seed clip used
            scenario: Scenario parameters (weather, lighting, actors, etc.)
            generation: Generation metadata (model, prompt, seed, etc.)
            validation: Optional validation results (verdict, realism score)
            
        Returns:
            The created entry dict
        """
        entry = {
            "clip_id": clip_id,
            "seed_id": seed_id,
            "scenario": scenario,
            "generation": generation,
            "validation": validation,
            "created_at": datetime.utcnow().isoformat(),
        }
        
        # Check for duplicates
        existing = self.get_entry(clip_id)
        if existing:
            # Update existing entry
            idx = next(i for i, e in enumerate(self.entries) if e["clip_id"] == clip_id)
            self.entries[idx] = entry
        else:
            self.entries.append(entry)
        
        return entry
    
    def get_entry(self, clip_id: str) -> Optional[Dict[str, Any]]:
        """Get an entry by clip ID."""
        for entry in self.entries:
            if entry["clip_id"] == clip_id:
                return entry
        return None
    
    def update_validation(
        self,
        clip_id: str,
        verdict: Dict[str, Any],
        realism_score: float,
        sut_output_path: Optional[str] = None,
    ):
        """Update the validation results for a clip.
        
        Args:
            clip_id: Clip to update
            verdict: Judge verdict dict
            realism_score: Realism score from evaluator
            sut_output_path: Path to system-under-test output
        """
        entry = self.get_entry(clip_id)
        if entry:
            entry["validation"] = {
                "verdict": verdict,
                "realism_score": realism_score,
                "sut_output_path": sut_output_path,
                "validated_at": datetime.utcnow().isoformat(),
            }
    
    def get_failures(self) -> List[Dict[str, Any]]:
        """Get all entries with failures."""
        failures = []
        for entry in self.entries:
            if entry.get("validation"):
                verdict = entry["validation"].get("verdict", {})
                if (not verdict.get("hazard_detected_in_time") or 
                    not verdict.get("action_safe")):
                    failures.append(entry)
        return failures
    
    def get_by_scenario(
        self,
        weather: Optional[str] = None,
        lighting: Optional[str] = None,
        actors: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Filter entries by scenario attributes."""
        results = []
        for entry in self.entries:
            scenario = entry.get("scenario", {})
            
            if weather and scenario.get("weather") != weather:
                continue
            if lighting and scenario.get("lighting") != lighting:
                continue
            if actors:
                entry_actors = scenario.get("actors", [])
                if not all(a in entry_actors for a in actors):
                    continue
            
            results.append(entry)
        return results
    
    def get_statistics(self) -> Dict[str, Any]:
        """Calculate summary statistics."""
        total = len(self.entries)
        validated = [e for e in self.entries if e.get("validation")]
        failures = self.get_failures()
        
        # Calculate average realism score
        realism_scores = [
            e["validation"]["realism_score"]
            for e in validated
            if e["validation"].get("realism_score") is not None
        ]
        avg_realism = sum(realism_scores) / len(realism_scores) if realism_scores else 0
        
        # Count failure categories
        failure_categories = {}
        for entry in failures:
            cat = entry["validation"]["verdict"].get("failure_category", "unknown")
            failure_categories[cat] = failure_categories.get(cat, 0) + 1
        
        return {
            "total_scenarios": total,
            "validated": len(validated),
            "failures": len(failures),
            "pass_rate": (len(validated) - len(failures)) / len(validated) if validated else 0,
            "average_realism_score": round(avg_realism, 3),
            "failure_categories": failure_categories,
        }
    
    def generate_clip_id(
        self,
        seed_id: str,
        scenario: Dict[str, Any],
        sequence_num: int,
    ) -> str:
        """Generate a unique clip ID from scenario parameters."""
        parts = [
            seed_id,
            scenario.get("weather", ""),
            scenario.get("lighting", ""),
            "_".join(scenario.get("actors", [])),
            scenario.get("behaviour", ""),
            f"{sequence_num:03d}",
        ]
        return "_".join(filter(None, parts))
    
    def export_for_report(self) -> Dict[str, Any]:
        """Export manifest data formatted for report generation."""
        stats = self.get_statistics()
        failures = self.get_failures()
        
        return {
            "summary": stats,
            "failures": [
                {
                    "clip_id": e["clip_id"],
                    "scenario": e["scenario"],
                    "verdict": e["validation"]["verdict"],
                    "realism_score": e["validation"].get("realism_score"),
                }
                for e in failures
            ],
            "generated_at": datetime.utcnow().isoformat(),
        }
