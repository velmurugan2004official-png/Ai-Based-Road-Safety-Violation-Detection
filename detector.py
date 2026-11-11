import cv2
from ultralytics import YOLO
from config import Config
import datetime
import os

SNAPSHOT_DIR = os.path.abspath(Config.VIOLATION_SAVE_PATH)

class ViolationDetector:
    def __init__(self):
        self.model = YOLO(Config.MODEL_PATH)
        self.confidence = Config.CONFIDENCE_THRESHOLD
        self.model_names = {
            int(class_id): self._normalize_class_name(name)
            for class_id, name in self.model.names.items()
        }
        self.detectable_classes = {
            "person", "bicycle", "car", "motorcycle", "bus", "truck",
            "cell_phone", "no_helmet", "without_helmet", "wrong_way",
            "no_parking", "illegal_parking",
        }
        self.prev_positions = {}
        self.parked_vehicles = {}
        os.makedirs(SNAPSHOT_DIR, exist_ok=True)
        print("✅ Detector initialized!")

    @staticmethod
    def _normalize_class_name(name):
        return str(name).strip().lower().replace("-", "_").replace(" ", "_")

    def detect_vehicles(self, frame):
        results = self.model(
            frame,
            conf=self.confidence,
            imgsz=Config.DETECTION_IMAGE_SIZE,
            verbose=False,
            augment=False,
            agnostic_nms=True,
        )
        detections = []
        for result in results:
            for box in result.boxes:
                cls = int(box.cls[0])
                conf = float(box.conf[0])
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                class_name = self.model_names.get(cls)
                if class_name in self.detectable_classes:
                    detections.append({
                        "class": class_name,
                        "confidence": round(conf, 2),
                        "bbox": (x1, y1, x2, y2)
                    })
        return detections

    def draw_detections(self, frame, detections):
        for det in detections:
            x1, y1, x2, y2 = det["bbox"]
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 200, 100), 2)
            cv2.putText(frame, f'{det["class"]} {det["confidence"]}',
                        (x1, y1-8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 100), 1)
        return frame

    def _draw_violation(self, frame, violation_type, bbox):
        if bbox is None:
            return frame

        height, width = frame.shape[:2]
        x1, y1, x2, y2 = (int(value) for value in bbox)
        x1 = max(0, min(x1, width - 1))
        x2 = max(0, min(x2, width - 1))
        y1 = max(0, min(y1, height - 1))
        y2 = max(0, min(y2, height - 1))
        if x2 <= x1 or y2 <= y1:
            return frame

        color = (0, 0, 255)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 4)
        label = f'VIOLATION: {violation_type.replace("_", " ").upper()}'
        (text_width, text_height), baseline = cv2.getTextSize(
            label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2
        )
        label_y = y1 - 8
        if label_y - text_height - baseline < 0:
            label_y = min(height - baseline - 1, y1 + text_height + 12)
        label_top = max(0, label_y - text_height - baseline - 6)
        label_right = min(width - 1, x1 + text_width + 10)
        cv2.rectangle(frame, (x1, label_top), (label_right, label_y + baseline), color, -1)
        cv2.putText(
            frame, label, (x1 + 5, label_y),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2,
        )
        return frame

    def save_violation_snapshot(self, frame, violation_type, bbox=None):
        """Save the full-resolution frame with a visible violation annotation."""
        snapshot = self._draw_violation(frame.copy(), violation_type, bbox)

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S%f")
        filename = f"{violation_type}_{timestamp}.jpg"
        saved = cv2.imwrite(os.path.join(SNAPSHOT_DIR, filename), snapshot)
        if not saved:
            raise OSError(f"Could not save violation snapshot: {filename}")
        return filename

    def check_no_helmet(self, detections):
        violations = []
        motorcycles = [d for d in detections if d["class"] == "motorcycle"]
        persons = [d for d in detections if d["class"] == "person"]
        for moto in motorcycles:
            mx1, my1, mx2, my2 = moto["bbox"]
            for p in persons:
                px1, py1, px2, py2 = p["bbox"]
                overlap = not (px2 < mx1 or px1 > mx2 or py2 < my1 or py1 > my2)
                if overlap:
                    violations.append({
                        "type": "no_helmet",
                        "bbox": p["bbox"],
                        "confidence": max(p["confidence"], moto["confidence"])
                    })
        return violations

    def check_phone_use(self, detections):
        violations = []
        phones = [d for d in detections if d["class"] == "cell_phone"]
        persons = [d for d in detections if d["class"] == "person"]
        motorcycles = [d for d in detections if d["class"] == "motorcycle"]
        for phone in phones:
            px1, py1, px2, py2 = phone["bbox"]
            phone_center = ((px1 + px2) / 2, (py1 + py2) / 2)
            for p in persons:
                bx1, by1, bx2, by2 = p["bbox"]
                is_on_person = (
                    bx1 <= phone_center[0] <= bx2 and
                    by1 <= phone_center[1] <= by1 + (by2 - by1) * 0.75
                )
                is_on_motorcycle = any(
                    bx1 < moto["bbox"][2] and bx2 > moto["bbox"][0]
                    and by2 > moto["bbox"][1]
                    for moto in motorcycles
                )
                if is_on_person and is_on_motorcycle:
                    violations.append({
                        "type": "phone_while_driving",
                        "bbox": p["bbox"],
                        "confidence": phone["confidence"]
                    })
        return violations

    def check_wrong_way(self, detections, frame_width=None):
        violations = []
        for det in detections:
            if det["class"] in ["car", "motorcycle", "truck", "bus"]:
                x1, y1, x2, y2 = det["bbox"]
                threshold = 40 if frame_width is None else max(40, frame_width * 0.08)
                if x1 < threshold:
                    violations.append({
                        "type": "wrong_way",
                        "bbox": det["bbox"],
                        "confidence": det["confidence"]
                    })
        return violations

    def check_no_parking(self, detections, frame_id):
        violations = []
        for det in detections:
            if det["class"] in ["car", "truck", "bus"]:
                cx = (det["bbox"][0] + det["bbox"][2]) // 2
                cy = (det["bbox"][1] + det["bbox"][3]) // 2
                key = f'{det["class"]}_{cx//50}'
                if key in self.parked_vehicles:
                    prev_id, prev_cx, prev_cy = self.parked_vehicles[key]
                    dist = ((cx-prev_cx)**2 + (cy-prev_cy)**2)**0.5
                    if dist < 15 and (frame_id - prev_id) > 40:
                        violations.append({
                            "type": "no_parking",
                            "bbox": det["bbox"],
                            "confidence": det["confidence"]
                        })
                self.parked_vehicles[key] = (frame_id, cx, cy)
        return violations

    def process_frame(self, frame, frame_id=0):
        detections = self.detect_vehicles(frame)
        violations = []
        violations.extend(self.check_no_helmet(detections))
        violations.extend(self.check_phone_use(detections))
        violations.extend(self.check_wrong_way(detections, frame.shape[1]))
        violations.extend(self.check_no_parking(detections, frame_id))
        frame = self.draw_detections(frame, detections)
        for violation in violations:
            self._draw_violation(frame, violation["type"], violation["bbox"])
        return frame, detections, violations
