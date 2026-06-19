"""Tests for the Scenario-Based Validation POC."""
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

# Enable mock mode for tests
os.environ["MOCK_MODE"] = "true"


class TestUtils:
    """Tests for utility functions."""
    
    def test_load_yaml(self):
        from utils import load_yaml
        
        # Create temp YAML file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("key: value\nlist:\n  - item1\n  - item2\n")
            f.flush()
            
            result = load_yaml(f.name)
            assert result["key"] == "value"
            assert result["list"] == ["item1", "item2"]
        
        os.unlink(f.name)
    
    def test_save_and_load_json(self):
        from utils import save_json, load_json
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            path = f.name
        
        data = {"key": "value", "number": 42, "list": [1, 2, 3]}
        save_json(data, path)
        
        loaded = load_json(path)
        assert loaded == data
        
        os.unlink(path)
    
    def test_generate_scenario_combinations(self):
        from utils import generate_scenario_combinations
        
        matrix = {
            "weather": ["clear", "rain"],
            "lighting": ["day", "night"],
            "actors": ["pedestrian"],
            "behaviour": ["jaywalk_cut_in"],
            "geometry": ["intersection"],
        }
        
        combos = list(generate_scenario_combinations(matrix, strategy="full"))
        
        # 2 * 2 * 1 * 1 * 1 = 4 combinations
        assert len(combos) == 4
        
        # Check structure
        for combo in combos:
            assert "weather" in combo
            assert "lighting" in combo
            assert "actors" in combo
            assert isinstance(combo["actors"], list)
    
    def test_ensure_dir(self):
        from utils import ensure_dir
        
        with tempfile.TemporaryDirectory() as tmpdir:
            new_dir = Path(tmpdir) / "subdir" / "nested"
            result = ensure_dir(str(new_dir))
            
            assert new_dir.exists()
            assert result == new_dir


class TestManifest:
    """Tests for the Manifest class."""
    
    def test_create_and_add_entry(self):
        from manifest import Manifest
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            path = f.name
        
        manifest = Manifest(path)
        
        manifest.add_entry(
            clip_id="test_001",
            seed_id="seed_001",
            scenario={"weather": "rain", "lighting": "night"},
            generation={"model": "test"},
        )
        
        assert len(manifest.entries) == 1
        assert manifest.entries[0]["clip_id"] == "test_001"
        
        manifest.save()
        
        # Reload and verify
        manifest2 = Manifest(path)
        assert len(manifest2.entries) == 1
        
        os.unlink(path)
    
    def test_update_validation(self):
        from manifest import Manifest
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            path = f.name
        
        manifest = Manifest(path)
        manifest.add_entry(clip_id="test_001", seed_id="seed_001")
        
        manifest.update_validation(
            clip_id="test_001",
            verdict="fail",
            realism_score=0.85,
            failure_category="late_detection",
            risk_score=7,
            rationale="Test failure",
        )
        
        entry = manifest.get_entry("test_001")
        assert entry["validation"]["verdict"] == "fail"
        assert entry["validation"]["risk_score"] == 7
        
        os.unlink(path)
    
    def test_statistics(self):
        from manifest import Manifest
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            path = f.name
        
        manifest = Manifest(path)
        
        # Add entries with mixed results
        manifest.add_entry(clip_id="pass_001", seed_id="s1")
        manifest.update_validation("pass_001", verdict="pass", realism_score=0.9)
        
        manifest.add_entry(clip_id="fail_001", seed_id="s2")
        manifest.update_validation(
            "fail_001", verdict="fail", realism_score=0.8,
            failure_category="late_detection"
        )
        
        manifest.add_entry(clip_id="fail_002", seed_id="s3")
        manifest.update_validation(
            "fail_002", verdict="fail", realism_score=0.7,
            failure_category="missed_detection"
        )
        
        stats = manifest.get_statistics()
        
        assert stats["total"] == 3
        assert stats["validated"] == 3
        assert stats["failures"] == 2
        assert stats["pass_rate"] == pytest.approx(1/3)
        assert stats["average_realism_score"] == pytest.approx(0.8)
        assert stats["failure_categories"]["late_detection"] == 1
        assert stats["failure_categories"]["missed_detection"] == 1
        
        os.unlink(path)


class TestCosmosWrapper:
    """Tests for Cosmos model wrappers (mock mode)."""
    
    def test_cosmos_predict_mock(self):
        from cosmos_wrapper import CosmosPredict
        
        model = CosmosPredict()
        result = model.generate(
            input_frames=["frame1", "frame2"],
            prompt="test prompt",
            num_frames=10,
        )
        
        assert "frames" in result
        assert "metadata" in result
        assert result["metadata"]["mock"] is True
    
    def test_cosmos_transfer_mock(self):
        from cosmos_wrapper import CosmosTransfer
        
        model = CosmosTransfer()
        result = model.generate(
            input_frames=["frame1"],
            control_inputs={"segmentation": None},
            prompt="test",
        )
        
        assert "frames" in result
        assert result["metadata"]["mock"] is True
    
    def test_cosmos_reason_mock(self):
        from cosmos_wrapper import CosmosReason
        
        model = CosmosReason()
        result = model.analyze(
            video_frames=["frame1", "frame2"],
            prompt="Describe the scene",
        )
        
        assert "text" in result
        assert result["metadata"]["mock"] is True


class TestJudge:
    """Tests for the Judge class."""
    
    def test_judge_evaluate_mock(self):
        from judge import Judge
        
        # Create temp rubric
        rubric_content = """
verdict:
  type: enum
  values: [pass, fail]
  
system_prompt: "You are a safety evaluator."
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(rubric_content)
            rubric_path = f.name
        
        judge = Judge(rubric_path=rubric_path)
        result = judge.evaluate(
            video_frames=["frame1", "frame2"],
            sut_output={"detections": [], "action": "maintain"},
            scenario_metadata={"weather": "rain"},
        )
        
        assert "verdict" in result
        assert result["verdict"] in ["pass", "fail"]
        
        os.unlink(rubric_path)


class TestEvaluator:
    """Tests for the Evaluator classes."""
    
    def test_realism_evaluator_mock(self):
        from evaluator import RealistmEvaluator
        
        evaluator = RealistmEvaluator()
        result = evaluator.score(frames=["frame1", "frame2"])
        
        assert "score" in result
        assert 0 <= result["score"] <= 1
    
    def test_artifact_detector_mock(self):
        from evaluator import ArtifactDetector
        
        detector = ArtifactDetector()
        result = detector.detect(frames=["frame1", "frame2"])
        
        assert "artifacts" in result
        assert "total_count" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
