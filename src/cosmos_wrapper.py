"""Thin wrappers around Cosmos model inference.

Supports MOCK_MODE for local development without GPU.
"""
import os
import json
from pathlib import Path
from typing import Optional, Dict, Any, List

MOCK_MODE = os.environ.get("MOCK_MODE", "0") == "1"


class CosmosPredict:
    """Wrapper for Cosmos Predict (world future generation)."""
    
    def __init__(self, checkpoint_path: Optional[str] = None):
        self.checkpoint_path = checkpoint_path
        self.model = None
        
        if not MOCK_MODE:
            self._load_model()
    
    def _load_model(self):
        """Load the Cosmos Predict model."""
        # Import only when not in mock mode
        try:
            # This will be the actual Cosmos import path
            # from cosmos_predict import CosmosPredict2_5
            # self.model = CosmosPredict2_5.from_pretrained(self.checkpoint_path)
            print(f"[CosmosPredict] Loading model from {self.checkpoint_path}")
            # Placeholder for actual model loading
        except ImportError as e:
            raise RuntimeError(
                "Cosmos Predict not installed. Run on GPU instance with Cosmos dependencies."
            ) from e
    
    def generate(
        self,
        input_frames: List[Any],
        prompt: str,
        num_frames: int = 150,
        guidance_scale: float = 7.5,
        seed: int = 42,
    ) -> Dict[str, Any]:
        """Generate future frames from input context.
        
        Args:
            input_frames: List of input frames (PIL Images or numpy arrays)
            prompt: Text prompt describing the desired scenario
            num_frames: Number of frames to generate
            guidance_scale: Classifier-free guidance scale
            seed: Random seed for reproducibility
            
        Returns:
            Dict with 'frames' (list of generated frames) and 'metadata'
        """
        if MOCK_MODE:
            return self._mock_generate(prompt, num_frames, seed)
        
        # Actual inference
        # output = self.model.generate(
        #     input_frames=input_frames,
        #     prompt=prompt,
        #     num_frames=num_frames,
        #     guidance_scale=guidance_scale,
        #     seed=seed,
        # )
        # return output
        raise NotImplementedError("Real inference not yet implemented")
    
    def _mock_generate(self, prompt: str, num_frames: int, seed: int) -> Dict[str, Any]:
        """Return mock output for local development."""
        return {
            "frames": [f"mock_frame_{i}.png" for i in range(num_frames)],
            "metadata": {
                "model": "cosmos-predict2.5-mock",
                "prompt": prompt,
                "num_frames": num_frames,
                "seed": seed,
            }
        }


class CosmosTransfer:
    """Wrapper for Cosmos Transfer (conditional generation with control inputs)."""
    
    def __init__(self, checkpoint_path: Optional[str] = None):
        self.checkpoint_path = checkpoint_path
        self.model = None
        
        if not MOCK_MODE:
            self._load_model()
    
    def _load_model(self):
        """Load the Cosmos Transfer model."""
        try:
            print(f"[CosmosTransfer] Loading model from {self.checkpoint_path}")
            # Placeholder for actual model loading
        except ImportError as e:
            raise RuntimeError(
                "Cosmos Transfer not installed. Run on GPU instance with Cosmos dependencies."
            ) from e
    
    def generate(
        self,
        input_frames: List[Any],
        control_inputs: Dict[str, Any],
        prompt: str,
        num_frames: int = 150,
        guidance_scale: float = 7.5,
        control_scale: float = 1.0,
        seed: int = 42,
    ) -> Dict[str, Any]:
        """Generate video conditioned on control inputs.
        
        Args:
            input_frames: List of input frames
            control_inputs: Dict with control signals (segmentation, depth, hdmap)
            prompt: Text prompt for the scenario
            num_frames: Number of frames to generate
            guidance_scale: Text guidance scale
            control_scale: Control input guidance scale
            seed: Random seed
            
        Returns:
            Dict with 'frames' and 'metadata'
        """
        if MOCK_MODE:
            return self._mock_generate(prompt, control_inputs, num_frames, seed)
        
        raise NotImplementedError("Real inference not yet implemented")
    
    def _mock_generate(
        self, prompt: str, control_inputs: Dict, num_frames: int, seed: int
    ) -> Dict[str, Any]:
        """Return mock output for local development."""
        return {
            "frames": [f"mock_transfer_frame_{i}.png" for i in range(num_frames)],
            "metadata": {
                "model": "cosmos-transfer2.5-mock",
                "prompt": prompt,
                "control_inputs": list(control_inputs.keys()),
                "num_frames": num_frames,
                "seed": seed,
            }
        }


class CosmosReason:
    """Wrapper for Cosmos Reason (vision-language reasoning)."""
    
    def __init__(self, checkpoint_path: Optional[str] = None):
        self.checkpoint_path = checkpoint_path
        self.model = None
        
        if not MOCK_MODE:
            self._load_model()
    
    def _load_model(self):
        """Load the Cosmos Reason model."""
        try:
            print(f"[CosmosReason] Loading model from {self.checkpoint_path}")
            # Placeholder for actual model loading
        except ImportError as e:
            raise RuntimeError(
                "Cosmos Reason not installed. Run on GPU instance with Cosmos dependencies."
            ) from e
    
    def analyze(
        self,
        video_frames: List[Any],
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 1024,
    ) -> Dict[str, Any]:
        """Analyze video and produce structured reasoning.
        
        Args:
            video_frames: List of video frames to analyze
            system_prompt: System instructions for the judge
            user_prompt: Specific question or analysis request
            max_tokens: Maximum response tokens
            
        Returns:
            Dict with 'response' (text) and 'metadata'
        """
        if MOCK_MODE:
            return self._mock_analyze(user_prompt)
        
        raise NotImplementedError("Real inference not yet implemented")
    
    def _mock_analyze(self, user_prompt: str) -> Dict[str, Any]:
        """Return mock analysis for local development."""
        # Return a realistic-looking mock verdict
        import random
        
        is_failure = random.random() > 0.4
        
        if is_failure:
            categories = ["late_detection", "missed_detection", "wrong_action"]
            category = random.choice(categories)
            risk = random.randint(3, 5)
            rationale = f"Mock failure: {category.replace('_', ' ')} detected in analysis."
        else:
            category = None
            risk = random.randint(1, 2)
            rationale = "Mock pass: System responded correctly with adequate margin."
        
        return {
            "response": json.dumps({
                "hazard_detected_in_time": not is_failure or category != "missed_detection",
                "action_safe": not is_failure or category not in ["wrong_action", "missed_detection"],
                "failure_category": category,
                "risk_score": risk,
                "rationale": rationale,
            }),
            "metadata": {
                "model": "cosmos-reason2-mock",
                "tokens_used": 256,
            }
        }
