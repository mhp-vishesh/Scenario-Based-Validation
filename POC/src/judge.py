"""Cosmos Reason judge with structured verdict output."""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

try:
    from .cosmos_wrapper import CosmosReason
except ImportError:
    from cosmos_wrapper import CosmosReason


class Judge:
    """Automated safety validation judge using Cosmos Reason."""
    
    def __init__(
        self,
        rubric_path: str = "config/judge_rubric.yaml",
        checkpoint_path: Optional[str] = None,
    ):
        self.rubric = self._load_rubric(rubric_path)
        self.reason_model = CosmosReason(checkpoint_path)
    
    def _load_rubric(self, path: str) -> Dict[str, Any]:
        """Load the judge rubric configuration."""
        with open(path) as f:
            return yaml.safe_load(f)
    
    def evaluate(
        self,
        video_frames: List[Any],
        sut_output: Dict[str, Any],
        scenario_metadata: Dict[str, Any],
        video_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Evaluate a scenario and produce a structured verdict.
        
        Args:
            video_frames: List of video frames from the generated scenario
            sut_output: Output from the system under test (detections, actions)
            scenario_metadata: Metadata about the scenario (weather, actors, etc.)
            video_path: Optional path to the clip. When given it is passed to the
                reason model, which samples the file directly (preferred over
                re-encoding frames).
            
        Returns:
            Structured verdict dict matching the rubric schema
        """
        # Build the user prompt with context
        user_prompt = self._build_prompt(sut_output, scenario_metadata)
        
        # Get analysis from Cosmos Reason
        result = self.reason_model.analyze(
            video_frames=video_frames,
            system_prompt=self.rubric.get("system_prompt", ""),
            user_prompt=user_prompt,
            video_path=video_path,
        )
        
        # Parse the structured response
        verdict = self._parse_verdict(result["response"])
        
        return {
            "verdict": verdict,
            "model_metadata": result.get("metadata", {}),
        }
    
    def _build_prompt(
        self, sut_output: Dict[str, Any], scenario_metadata: Dict[str, Any]
    ) -> str:
        """Build the analysis prompt with scenario context."""
        definitions = self.rubric.get("failure_definitions", {}) or {}
        category_lines = "\n".join(
            f"  - {name}: {desc}" for name, desc in definitions.items()
        )
        prompt = f"""
Analyze this driving scenario and the system-under-test's response.

Scenario context:
- Weather: {scenario_metadata.get('weather', 'unknown')}
- Lighting: {scenario_metadata.get('lighting', 'unknown')}
- Actors present: {', '.join(scenario_metadata.get('actors', []))}
- Actor behaviour: {scenario_metadata.get('behaviour', 'unknown')}
- Road geometry: {scenario_metadata.get('geometry', 'unknown')}

System-under-test output:
- Detections: {json.dumps(sut_output.get('detections', []))}
- Chosen action: {sut_output.get('action', 'unknown')}
- Detection frame: {sut_output.get('detection_frame', 'N/A')}
- Action frame: {sut_output.get('action_frame', 'N/A')}

Evaluate whether the system detected the hazard in time and took appropriate action.
Return your verdict as a JSON object with these fields:
- hazard_detected_in_time (bool)
- action_safe (bool)
- failure_category: choose exactly one of the labels below, or null only when both
  hazard_detected_in_time and action_safe are true (a passing scenario). Do not
  invent other labels and do not return "unknown".
{category_lines}
- risk_score (int 1-5)
- rationale (string)
"""
        return prompt
    
    def _parse_verdict(self, response: str) -> Dict[str, Any]:
        """Parse the model's response into a structured verdict."""
        try:
            # Try to parse as JSON directly
            verdict = json.loads(response)
        except json.JSONDecodeError:
            # Try to extract JSON from the response
            import re
            json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
            if json_match:
                verdict = json.loads(json_match.group())
            else:
                # Fallback to a default failed parse
                verdict = {
                    "hazard_detected_in_time": None,
                    "action_safe": None,
                    "failure_category": "parse_error",
                    "risk_score": 5,
                    "rationale": f"Failed to parse model response: {response[:200]}",
                }
        
        # Validate and sanitize
        verdict = self._validate_verdict(verdict)
        return verdict
    
    def _validate_verdict(self, verdict: Dict[str, Any]) -> Dict[str, Any]:
        """Validate verdict against the schema."""
        schema = self.rubric.get("verdict_schema", {})
        
        # Ensure required fields exist
        validated = {
            "hazard_detected_in_time": verdict.get("hazard_detected_in_time"),
            "action_safe": verdict.get("action_safe"),
            "failure_category": verdict.get("failure_category"),
            "risk_score": verdict.get("risk_score", 3),
            "rationale": verdict.get("rationale", "No rationale provided"),
        }
        
        # Clamp risk score to valid range
        validated["risk_score"] = max(1, min(5, validated["risk_score"]))
        
        # Validate failure category
        fc = validated["failure_category"]
        if isinstance(fc, str):
            fc = fc.strip().lower()
            if fc in ("", "none", "null", "n/a", "na"):
                fc = None
            validated["failure_category"] = fc
        allowed = schema.get("failure_category", {}).get("allowed_values", [])
        if (
            allowed
            and validated["failure_category"] is not None
            and validated["failure_category"] not in allowed
        ):
            validated["failure_category"] = "unknown"

        return validated
    
    def batch_evaluate(
        self,
        scenarios: List[Dict[str, Any]],
        progress_callback: Optional[callable] = None,
    ) -> List[Dict[str, Any]]:
        """Evaluate multiple scenarios.
        
        Args:
            scenarios: List of scenario dicts with 'frames', 'sut_output', 'metadata'
            progress_callback: Optional callback(current, total) for progress updates
            
        Returns:
            List of verdict dicts
        """
        results = []
        total = len(scenarios)
        
        for i, scenario in enumerate(scenarios):
            result = self.evaluate(
                video_frames=scenario.get("frames", []),
                sut_output=scenario.get("sut_output", {}),
                scenario_metadata=scenario.get("metadata", {}),
            )
            results.append(result)
            
            if progress_callback:
                progress_callback(i + 1, total)
        
        return results
