import datetime
from app.alerts.logger import ViolationLogger

class AlertSystem:
    def __init__(self):
        self.logger = ViolationLogger()
        self.alert_cooldown = {}
        self.cooldown_seconds = 5
        print("✅ Alert system initialized!")

    def _is_cooldown_active(self, violation_type):
        now = datetime.datetime.now()
        if violation_type in self.alert_cooldown:
            if (now - self.alert_cooldown[violation_type]).seconds < self.cooldown_seconds:
                return True
        self.alert_cooldown[violation_type] = now
        return False

    def trigger_alert(self, violation_type, confidence, snapshot_path=None):
        if self._is_cooldown_active(violation_type):
            return None
        return self.logger.log_violation(violation_type, confidence, snapshot_path)

    def process_violations(self, violations, frame, detector):
        alerts = []
        for v in violations:
            snapshot = detector.save_violation_snapshot(
                frame, v["type"], bbox=v.get("bbox")
            )
            alert = self.trigger_alert(v["type"], v["confidence"], snapshot)
            if alert:
                alerts.append(alert)
        return alerts

    def get_summary(self):
        return self.logger.get_violation_summary()

    def get_all(self):
        return self.logger.get_all_violations()
