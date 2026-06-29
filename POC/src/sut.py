"""System Under Test (SUT) wrapper using YOLO v8 for object detection.

This module wraps YOLO v8 to detect pedestrians, vehicles, and other road users
in generated scenario clips. The judge then evaluates whether detections were
made correctly and in time.
"""
from typing import Any, Dict, List, Optional


class YOLOv8Detector:
    """YOLO v8 based object detector for ADAS validation.
    
    Detects:
    - person (pedestrians, cyclists)
    - car, truck, bus (vehicles)
    - motorcycle, bicycle
    - traffic light, stop sign
    """
    
    # COCO classes relevant to ADAS
    ADAS_CLASSES = {
        0: "person",
        1: "bicycle", 
        2: "car",
        3: "motorcycle",
        5: "bus",
        7: "truck",
        9: "traffic light",
        11: "stop sign",
    }
    
    # Hazard classes that require detection
    HAZARD_CLASSES = {"person", "bicycle", "motorcycle"}
    
    def __init__(self, model_name: str = "yolov8n.pt", confidence: float = 0.5):
        """Initialize YOLO v8 detector.
        
        Args:
            model_name: YOLO model variant (yolov8n/s/m/l/x.pt)
            confidence: Minimum confidence threshold
        """
        self.model_name = model_name
        self.confidence = confidence
        self.model = None
        self._load_model()
    
    def _load_model(self):
        """Load the YOLO model."""
        try:
            from ultralytics import YOLO
            self.model = YOLO(self.model_name)
            print(f"[SUT] Loaded YOLO v8 model: {self.model_name}")
        except ImportError:
            print("[SUT] Warning: ultralytics not installed. Run: pip install ultralytics")
            self.model = None
        except Exception as e:
            print(f"[SUT] Error loading model: {e}")
            self.model = None
    
    def detect_frame(self, frame) -> Dict[str, Any]:
        """Run detection on a single frame.
        
        Args:
            frame: Image as numpy array, PIL Image, or file path
            
        Returns:
            Dict with detections and metadata
        """
        if self.model is None:
            return {
                "detections": [],
                "hazards_detected": 0,
                "total_detections": 0,
            }
        
        # Run inference
        results = self.model(frame, conf=self.confidence, verbose=False)
        
        detections = []
        for result in results:
            boxes = result.boxes
            for i in range(len(boxes)):
                cls_id = int(boxes.cls[i])
                if cls_id in self.ADAS_CLASSES:
                    det = {
                        "class": self.ADAS_CLASSES[cls_id],
                        "class_id": cls_id,
                        "confidence": float(boxes.conf[i]),
                        "bbox": boxes.xyxy[i].tolist(),  # [x1, y1, x2, y2]
                        "is_hazard": self.ADAS_CLASSES[cls_id] in self.HAZARD_CLASSES,
                    }
                    detections.append(det)
        
        return {
            "detections": detections,
            "hazards_detected": sum(1 for d in detections if d["is_hazard"]),
            "total_detections": len(detections),
        }
    
    def detect_video(self, frames: List) -> Dict[str, Any]:
        """Run detection on a video (list of frames).
        
        Args:
            frames: List of frames (numpy arrays or PIL Images)
            
        Returns:
            Dict with per-frame detections and aggregated results
        """
        if not frames:
            return self._empty_result()
        
        frame_results = []
        first_hazard_frame = None
        total_hazards = 0
        
        for i, frame in enumerate(frames):
            result = self.detect_frame(frame)
            result["frame_index"] = i
            frame_results.append(result)
            
            if result["hazards_detected"] > 0:
                total_hazards += result["hazards_detected"]
                if first_hazard_frame is None:
                    first_hazard_frame = i
        
        # Determine action based on detections
        if first_hazard_frame is not None:
            # Hazard detected - determine if response is timely
            # Assume 30 fps, response should be within 1 second (30 frames)
            response_time_frames = first_hazard_frame
            action = "brake" if response_time_frames < len(frames) * 0.7 else "late_brake"
        else:
            action = "maintain"
        
        return {
            "frame_results": frame_results,
            "first_hazard_frame": first_hazard_frame,
            "total_hazards_detected": total_hazards,
            "num_frames": len(frames),
            "action": action,
            "model": self.model_name,
        }
    
    def _empty_result(self) -> Dict[str, Any]:
        """Return empty result structure."""
        return {
            "frame_results": [],
            "first_hazard_frame": None,
            "total_hazards_detected": 0,
            "num_frames": 0,
            "action": "maintain",
            "model": self.model_name,
        }


class SystemUnderTest:
    """Generic SUT interface wrapping the detector with decision logic."""
    
    def __init__(self, detector: Optional[YOLOv8Detector] = None):
        """Initialize SUT with a detector.
        
        Args:
            detector: Object detector instance. Defaults to YOLOv8.
        """
        self.detector = detector or YOLOv8Detector()
    
    def run(self, video_frames: List) -> Dict[str, Any]:
        """Run the full perception and decision pipeline on a video.
        
        Args:
            video_frames: List of video frames
            
        Returns:
            Dict with detections, chosen action, timing info
        """
        # Run detection
        detection_result = self.detector.detect_video(video_frames)
        
        # Add decision metadata
        result = {
            "detections": detection_result.get("frame_results", []),
            "action": detection_result.get("action", "maintain"),
            "detection_frame": detection_result.get("first_hazard_frame"),
            "action_frame": None,
            "model": detection_result.get("model", "unknown"),
            "total_hazards": detection_result.get("total_hazards_detected", 0),
            "num_frames": detection_result.get("num_frames", 0),
        }
        
        # Calculate action frame (detection + reaction time)
        if result["detection_frame"] is not None:
            # Assume 5 frame reaction delay
            result["action_frame"] = result["detection_frame"] + 5
        
        return result


# Convenience function
def create_sut(model: str = "yolov8n.pt", confidence: float = 0.5) -> SystemUnderTest:
    """Create a System Under Test instance.
    
    Args:
        model: YOLO model variant
        confidence: Detection confidence threshold
        
    Returns:
        Configured SystemUnderTest instance
    """
    detector = YOLOv8Detector(model_name=model, confidence=confidence)
    return SystemUnderTest(detector)
