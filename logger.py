
import logging
import os
import json
import csv
import datetime
from config import Config

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

log_dir = os.path.dirname(Config.LOG_PATH)
if log_dir:
    os.makedirs(log_dir, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(Config.LOG_PATH),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class ViolationLogger:
    def __init__(self):
        self.violations_db = []
        self.db_path = os.path.join(LOG_DIR, "violations_db.json")
        self._load_from_disk()
        print("Logger initialized!")

    def _load_from_disk(self):
        if not os.path.exists(self.db_path):
            return

        try:
            with open(self.db_path, "r", encoding="utf-8") as file:
                data = json.load(file)

            if not isinstance(data, list):
                raise ValueError("Violation database must contain a JSON list.")

            self.violations_db = data

            # Add fields required by the case-review page to old records.
            for record in self.violations_db:
                record.setdefault("status", "pending")
                record.setdefault("fine", 0)
                record.setdefault("note", "")
                record.setdefault("reviewed_at", None)

            self._save_to_disk()
            print(f"Loaded {len(self.violations_db)} existing violations")

        except (OSError, json.JSONDecodeError, ValueError) as error:
            # Do not overwrite a database that could not be read.
            logger.error("Could not load violations database: %s", error)
            raise

    def _save_to_disk(self):
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)

        # Write first to a temporary file, then replace the database.
        temporary_path = self.db_path + ".tmp"
        with open(temporary_path, "w", encoding="utf-8") as file:
            json.dump(self.violations_db, file, indent=4)
        os.replace(temporary_path, self.db_path)

    def log_violation(self, violation_type, confidence, snapshot_path=None):
        next_id = max(
            (record.get("id", 0) for record in self.violations_db),
            default=0
        ) + 1

        record = {
            "id": next_id,
            "type": violation_type,
            "confidence": confidence,
            "timestamp": datetime.datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "snapshot": snapshot_path or "N/A",
            "status": "pending",
            "fine": 0,
            "note": "",
            "reviewed_at": None
        }

        self.violations_db.append(record)
        self._save_to_disk()

        logger.warning(
            "VIOLATION: %s | Confidence: %s",
            violation_type,
            confidence
        )
        return record

    def get_all_violations(self):
        return self.violations_db

    def get_violation_summary(self):
        summary = {}
        for record in self.violations_db:
            violation_type = record.get("type", "unknown")
            summary[violation_type] = summary.get(violation_type, 0) + 1
        return summary

    def review(self, violation_id, status, note=""):
        if status not in ("pending", "confirmed", "rejected"):
            return None

        record = next(
            (
                item for item in self.violations_db
                if item.get("id") == violation_id
            ),
            None
        )

        if record is None:
            return None

        record["status"] = status
        record["note"] = note
        record["reviewed_at"] = datetime.datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        self._save_to_disk()
        return record

    def export_to_json(self, output_path="logs/violations_export.json"):
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as file:
            json.dump(self.violations_db, file, indent=4)

    def export_csv(self, output_path="logs/violations_export.csv"):
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        columns = [
            "id", "type", "confidence", "timestamp", "snapshot",
            "status", "fine", "note", "reviewed_at"
        ]

        with open(output_path, "w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=columns)
            writer.writeheader()
            writer.writerows(self.violations_db)

        return output_path

    def clear_logs(self):
        self.violations_db = []
        self._save_to_disk()
