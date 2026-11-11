import cv2
import threading
from config import Config

class VideoHandler:
    def __init__(self):
        self.cap = None
        self.is_running = False
        self.lock = threading.Lock()

    def start_camera(self):
        self.cap = cv2.VideoCapture(Config.CAMERA_INDEX)
        if not self.cap.isOpened():
            print("❌ Camera not found!")
            return False
        self.is_running = True
        print("✅ Camera started!")
        return True

    def start_video_file(self, filepath):
        self.cap = cv2.VideoCapture(filepath)
        if not self.cap.isOpened():
            print(f"❌ Could not open: {filepath}")
            return False
        self.is_running = True
        print(f"✅ Video loaded: {filepath}")
        return True

    def read_frame(self):
        if self.cap is None or not self.is_running:
            return False, None
        ret, frame = self.cap.read()
        if not ret:
            print("⚠️ End of video or frame read error")
            self.is_running = False
            return False, None
        return True, frame

    def get_video_info(self):
        if self.cap is None:
            return {}
        return {
            "width":  int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "height": int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            "fps":    int(self.cap.get(cv2.CAP_PROP_FPS)),
            "total_frames": int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        }

    def release(self):
        self.is_running = False
        if self.cap:
            self.cap.release()
        print("✅ Video handler released!")

    def generate_frames(self, detector):
        frame_id = 0
        while self.is_running:
            ret, frame = self.read_frame()
            if not ret:
                break
            frame_id += 1
            if frame_id % Config.FRAME_SKIP != 0:
                continue
            processed, _, _ = detector.process_frame(frame)
            _, buffer = cv2.imencode('.jpg', processed, [cv2.IMWRITE_JPEG_QUALITY, 80])
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' +
                   buffer.tobytes() + b'\r\n')
