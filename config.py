import os
from dotenv import load_dotenv
load_dotenv()

class Config:
    DEBUG = False
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", 5001))
    CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", 0.25))
    MODEL_PATH = os.getenv("MODEL_PATH", "models/yolov8n.pt")
    DETECTION_IMAGE_SIZE = int(os.getenv("DETECTION_IMAGE_SIZE", 320))
    FRAME_SKIP = int(os.getenv("FRAME_SKIP", 3))
    VIOLATION_SAVE_PATH = os.getenv("VIOLATION_SAVE_PATH", "static/violations")
    LOG_PATH = os.getenv("LOG_PATH", "logs/violations.log")
    CAMERA_INDEX = int(os.getenv("CAMERA_INDEX", 0))
