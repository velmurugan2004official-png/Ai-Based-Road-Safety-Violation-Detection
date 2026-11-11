
import os
from flask import (
    jsonify, request, render_template, redirect, url_for, send_file, abort
)
from flask_login import login_required, current_user

from app.dashboard.routes import app, alert_system


log = alert_system.logger


def admin_required():
    if not current_user.is_authenticated:
        abort(401)
    if current_user.role != "admin":
        abort(403)


def _row(record):
    row = dict(record)
    snapshot = row.get("snapshot")

    row["snapshot_file"] = (
        os.path.basename(snapshot)
        if snapshot and snapshot != "N/A"
        else None
    )
    row["label"] = row.get("type", "Unknown").replace("_", " ").title()

    # Keep existing records compatible with the review template.
    row.setdefault("status", "pending")
    row.setdefault("fine", 0)
    row.setdefault("note", "")
    row.setdefault("reviewed_at", None)
    row.setdefault("tier", "Unassigned")
    row.setdefault("section", "Unassigned")
    row.setdefault("trace", "")

    return row


@app.route('/review')
@login_required
def review_page():
    return render_template('review.html')


@app.route('/api/cases')
@login_required
def api_cases():
    status = request.args.get('status', '').strip()
    violation_type = request.args.get('type', '').strip()
    query = request.args.get('q', '').strip().lower()

    if status and status not in ('pending', 'confirmed', 'rejected'):
        return jsonify({"error": "Invalid status filter"}), 400

    records = reversed(log.get_all_violations())
    results = []

    for record in records:
        row = _row(record)

        if status and row["status"] != status:
            continue
        if violation_type and row["type"] != violation_type:
            continue

        searchable = (
            str(row.get("type", "")) + " " +
            str(row.get("timestamp", "")) + " " +
            str(row.get("id", "")) + " " +
            str(row.get("note", ""))
        ).lower()

        if query and query not in searchable:
            continue

        results.append(row)

    return jsonify(results)


@app.route('/api/stats')
@login_required
def api_stats():
    records = log.get_all_violations()

    pending = sum(1 for r in records if r.get("status", "pending") == "pending")
    confirmed = sum(1 for r in records if r.get("status") == "confirmed")
    rejected = sum(1 for r in records if r.get("status") == "rejected")

    fine_total = sum(
        (r.get("fine", 0) or 0)
        for r in records
        if r.get("status") == "confirmed"
    )

    return jsonify(
        total=len(records),
        pending=pending,
        confirmed=confirmed,
        rejected=rejected,
        fine=fine_total
    )


@app.route('/api/review/<int:vid>', methods=['POST'])
@login_required
def api_review(vid):
    data = request.get_json(silent=True) or {}
    status = data.get("status")
    note = str(data.get("note", "")).strip()

    if status not in ("pending", "confirmed", "rejected"):
        return jsonify({"error": "Invalid review status"}), 400

    if len(note) > 1000:
        return jsonify({"error": "Note must be 1000 characters or fewer"}), 400

    record = next(
        (r for r in log.get_all_violations() if r.get("id") == vid),
        None
    )
    if record is None:
        return jsonify({"error": "Violation not found"}), 404

    # Only administrators can confirm or reject cases.
    if status in ("confirmed", "rejected"):
        admin_required()

    updated = log.review(vid, status, note)
    if updated is None:
        return jsonify({"error": "Could not update review"}), 400

    return jsonify(_row(updated))


@app.route('/api/set_fine/<int:vid>', methods=['POST'])
@login_required
def api_set_fine(vid):
    admin_required()
    data = request.get_json(silent=True) or {}
    fine = data.get("fine", 0)

    try:
        fine = int(fine)
        if fine < 0:
            return jsonify({"error": "Fine cannot be negative"}), 400
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid fine amount"}), 400

    record = next(
        (r for r in log.get_all_violations() if r.get("id") == vid),
        None
    )
    if record is None:
        return jsonify({"error": "Violation not found"}), 404

    record["fine"] = fine
    log._save_to_disk()

    return jsonify({"status": "updated", "id": vid, "fine": fine})


@app.route('/export/csv')
@login_required
def export_csv():
    filepath = os.path.abspath(log.export_csv())
    if not os.path.isfile(filepath):
        return jsonify({"error": "Export file not found"}), 404

    return send_file(filepath, as_attachment=True)


@app.route('/challan/<int:vid>')
@login_required
def challan(vid):
    record = next(
        (r for r in log.get_all_violations() if r.get("id") == vid),
        None
    )

    if record is None:
        return "Violation not found.", 404

    if record.get("status") != "confirmed":
        return "Confirm the violation before generating a challan.", 400

    # Only administrators can generate challans in this version.
    admin_required()

    return render_template('challan.html', v=_row(record))
