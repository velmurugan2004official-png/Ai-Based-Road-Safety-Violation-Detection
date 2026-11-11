
import os
import cv2
import threading

from flask import (
    Flask, render_template, Response, jsonify, request,
    send_file, flash, url_for, redirect, abort
)
from flask_socketio import SocketIO
from flask_login import (
    login_user, logout_user, login_required, current_user
)
from werkzeug.utils import secure_filename

from app.detection import ViolationDetector, VideoHandler
from app.alerts import AlertSystem
from config import Config
from app.dashboard.auth import db, User, init_auth
from werkzeug.security import generate_password_hash


app = Flask(__name__, template_folder='../../templates')

app.config['SECRET_KEY'] = os.getenv("SECRET_KEY")
if not app.config["SECRET_KEY"]:
    raise RuntimeError(
        "SECRET_KEY is missing. Add it to your .env file before starting the app."
    )

init_auth(app)

socketio = SocketIO(app, cors_allowed_origins="*")

detector = ViolationDetector()
video_handler = VideoHandler()
alert_system = AlertSystem()

UPLOAD_FOLDER = os.path.abspath('dataset/videos')
OUTPUT_VIDEO = os.path.abspath('static/violations/output_detected.mp4')
SNAPSHOT_DIR = os.path.abspath(Config.VIOLATION_SAVE_PATH)

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(SNAPSHOT_DIR, exist_ok=True)


# ---------------- AUTHENTICATION ----------------

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if not username or not password:
            flash('Username and password are required.', 'error')
        elif len(username) > 80:
            flash('Username must be 80 characters or fewer.', 'error')
        elif len(password) < 8:
            flash('Password must be at least 8 characters.', 'error')
        elif User.query.filter_by(username=username).first():
            flash('That username is already registered.', 'error')
        else:
            user = User(username=username, role='officer')
            user.set_password(password)
            db.session.add(user)
            db.session.commit()

            flash('Registration successful. Please log in.', 'success')
            return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('index'))

        flash('Invalid username or password.', 'error')

    return render_template('login.html')


@app.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))


def admin_required():
    if not current_user.is_authenticated:
        abort(401)
    if current_user.role != 'admin':
        abort(403)


# ---------------- MAIN DASHBOARD ----------------

@app.route('/')
@login_required
def index():
    return render_template('index.html')


@app.route('/history')
@login_required
def history():
    return redirect(url_for('review_page'))


# ---------------- CAMERA AND VIDEO ----------------

@app.route('/video_feed')
@login_required
def video_feed():
    return Response(
        video_handler.generate_frames(detector),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )


@app.route('/start_camera', methods=['POST'])
@login_required
def start_camera():
    success = video_handler.start_camera()
    return jsonify({
        "status": "started" if success else "failed"
    })


@app.route('/upload_video', methods=['POST'])
@login_required
def upload_video():
    file = request.files.get('video')

    if not file or not file.filename:
        return jsonify({
            "status": "error",
            "message": "Please select a video file."
        }), 400

    filename = secure_filename(file.filename)

    if not filename:
        return jsonify({
            "status": "error",
            "message": "Invalid filename."
        }), 400

    if not filename.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
        return jsonify({
            "status": "error",
            "message": "Unsupported video format."
        }), 400

    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)

    return jsonify({
        "status": "uploaded",
        "filename": filename
    })


@app.route('/uploaded_video/<filename>')
@login_required
def uploaded_video(filename):
    filename = secure_filename(filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)

    if not filename or not os.path.isfile(filepath):
        abort(404)

    return send_file(filepath)


# Track detection progress
detection_status = {"running": False, "progress": 0, "total": 0}

@app.route('/detection_progress')
@login_required
def detection_progress():
    return jsonify(detection_status)


@app.route('/run_detection/<filename>', methods=['POST'])
@login_required
def run_detection(filename):
    filename = secure_filename(filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)

    if not filename or not os.path.isfile(filepath):
        return jsonify({
            "status": "error",
            "message": "Video not found."
        }), 404

    # Run in background — do NOT join (no blocking!)
    thread = threading.Thread(
        target=process_video_file,
        args=(filepath,),
        daemon=True
    )
    thread.start()

    return jsonify({"status": "processing"})


def process_video_file(filepath):
    global detection_status
    detection_status = {"running": True, "progress": 0, "total": 0}

    video_handler.start_video_file(filepath)
    info = video_handler.get_video_info()

    if not info or not info.get('width') or not info.get('height'):
        video_handler.release()
        detection_status["running"] = False
        print("Could not read video information.")
        return

    # ── KEY FIX: Resize 4K video to max 640px wide for speed ──
    orig_w = info['width']
    orig_h = info['height']
    max_width = 640
    if orig_w > max_width:
        scale = max_width / orig_w
        proc_w = max_width
        proc_h = int(orig_h * scale)
    else:
        scale = 1.0
        proc_w = orig_w
        proc_h = orig_h

    total_frames = info.get('total_frames', 0)
    detection_status["total"] = total_frames

    fourcc = cv2.VideoWriter_fourcc(*'avc1')
    fps = info['fps'] if info['fps'] > 0 else 12

    out = cv2.VideoWriter(
        OUTPUT_VIDEO,
        fourcc,
        fps,
        (orig_w, orig_h)
    )

    try:
        frame_id = 0

        while video_handler.is_running:
            ret, frame = video_handler.read_frame()

            if not ret:
                break

            frame_id += 1
            detection_status["progress"] = frame_id

            # Skip frames — write original unprocessed
            if frame_id % Config.FRAME_SKIP != 0:
                out.write(frame)
                continue

            # ── Resize small for fast inference ──
            small = cv2.resize(frame, (proc_w, proc_h))
            processed_small, _, violations = detector.process_frame(
                small, frame_id
            )

            # ── Scale violations bbox back to original size ──
            if violations and scale != 1.0:
                scaled = []
                for v in violations:
                    x1, y1, x2, y2 = v['bbox']
                    scaled.append({
                        **v,
                        'bbox': (
                            int(x1 / scale), int(y1 / scale),
                            int(x2 / scale), int(y2 / scale)
                        )
                    })
                violations = scaled

            if violations:
                alert_system.process_violations(
                    violations, frame, detector
                )

            # Scale processed frame back to original size
            processed = cv2.resize(processed_small, (orig_w, orig_h))
            out.write(processed)

    finally:
        out.release()
        video_handler.release()
        alert_system.logger.export_to_json()
        detection_status["running"] = False

    print(
        f"Detection finished. "
        f"{len(alert_system.get_all())} violations saved."
    )


@app.route('/output_video')
@login_required
def output_video():
    if not os.path.isfile(OUTPUT_VIDEO):
        return jsonify({"error": "Output video not available."}), 404

    return send_file(OUTPUT_VIDEO, mimetype='video/mp4')


@app.route('/stop', methods=['POST'])
@login_required
def stop():
    video_handler.release()
    return jsonify({"status": "stopped"})


# ---------------- VIOLATIONS AND SNAPSHOTS ----------------

@app.route('/violations')
@login_required
def get_violations():
    return jsonify(alert_system.get_all())


@app.route('/summary')
@login_required
def get_summary():
    return jsonify(alert_system.get_summary())


@app.route('/snapshots')
@login_required
def get_snapshots():
    files = [
        filename for filename in os.listdir(SNAPSHOT_DIR)
        if filename.lower().endswith('.jpg')
        and os.path.isfile(os.path.join(SNAPSHOT_DIR, filename))
    ]
    return jsonify(sorted(files))


@app.route('/snapshot/<filename>')
@login_required
def get_snapshot(filename):
    filename = secure_filename(filename)

    if not filename or not filename.lower().endswith('.jpg'):
        abort(404)

    filepath = os.path.join(SNAPSHOT_DIR, filename)

    if not os.path.isfile(filepath):
        return jsonify({"error": "Not found"}), 404

    return send_file(filepath, mimetype='image/jpeg')


@app.route('/clear', methods=['POST'])
@login_required
def clear():
    admin_required()

    alert_system.logger.clear_logs()

    for filename in os.listdir(SNAPSHOT_DIR):
        if filename.lower().endswith('.jpg'):
            filepath = os.path.join(SNAPSHOT_DIR, filename)
            if os.path.isfile(filepath):
                os.remove(filepath)

    return jsonify({"status": "cleared"})


@app.route('/video_info')
@login_required
def video_info():
    return jsonify(video_handler.get_video_info())
