"""
Officer blueprint — for users with role='officer'.
Officers can: view their appointments, approve/reject, scan QR for check-in,
set unavailability, mark as completed.
"""
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from models import db, Appointment, Officer, Notification, User, OfficerUnavailability, AuditLog
from datetime import datetime, date, timezone

officer_bp = Blueprint('officer', __name__, url_prefix='/officer')

def officer_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ('officer', 'admin', 'super_admin'):
            flash('Access denied.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated

def get_officer_record():
    """Get the Officer DB record linked to the current logged-in officer user."""
    return Officer.query.filter_by(email=current_user.email).first()

# ── Dashboard ──────────────────────────────────────────────────────────────────
@officer_bp.route('/')
@login_required
@officer_required
def dashboard():
    officer = get_officer_record()
    if not officer:
        flash('No officer profile linked to your account. Contact an administrator.', 'warning')
        return render_template('officer/dashboard.html', officer=None, today_apts=[], pending=[], stats={})

    today = datetime.now(timezone.utc).date()
    today_apts = Appointment.query.filter_by(officer_id=officer.id, date=today)\
        .order_by(Appointment.time).all()
    pending = Appointment.query.filter_by(officer_id=officer.id, status='Pending')\
        .order_by(Appointment.date, Appointment.time).all()

    stats = {
        'total':     Appointment.query.filter_by(officer_id=officer.id).count(),
        'pending':   Appointment.query.filter_by(officer_id=officer.id, status='Pending').count(),
        'approved':  Appointment.query.filter_by(officer_id=officer.id, status='Approved').count(),
        'completed': Appointment.query.filter_by(officer_id=officer.id, status='Completed').count(),
        'rejected':  Appointment.query.filter_by(officer_id=officer.id, status='Rejected').count(),
        'today':     len(today_apts),
    }
    return render_template('officer/dashboard.html', officer=officer,
                           today_apts=today_apts, pending=pending, stats=stats, today=today)

# ── Approve appointment ────────────────────────────────────────────────────────
@officer_bp.route('/approve/<int:apt_id>')
@login_required
@officer_required
def approve(apt_id):
    apt = db.session.get(Appointment, apt_id)
    officer = get_officer_record()
    if not apt or (officer and apt.officer_id != officer.id):
        flash('Not authorized.', 'danger')
        return redirect(url_for('officer.dashboard'))
    apt.status = 'Approved'
    msg = f"Your appointment with {apt.officer.name} on {apt.date.strftime('%d %b %Y')} at {apt.time} has been Approved."
    db.session.add(Notification(user_id=apt.user_id, message=msg))
    db.session.add(AuditLog(admin_id=current_user.id, action='approve',
                             detail=f"#{apt.id} {apt.student_name} → Approved"))
    db.session.commit()
    from utils import send_email, appointment_status_email
    student = db.session.get(User, apt.user_id)
    send_email('Appointment Approved — IUT', [student.email], appointment_status_email(apt, 'Approved'))
    flash('Appointment approved.', 'success')
    return redirect(request.referrer or url_for('officer.dashboard'))

# ── Reject appointment ─────────────────────────────────────────────────────────
@officer_bp.route('/reject/<int:apt_id>', methods=['POST'])
@login_required
@officer_required
def reject(apt_id):
    apt = db.session.get(Appointment, apt_id)
    officer = get_officer_record()
    if not apt or (officer and apt.officer_id != officer.id):
        flash('Not authorized.', 'danger')
        return redirect(url_for('officer.dashboard'))
    note = request.form.get('note', '').strip()
    apt.status = 'Rejected'
    apt.rejection_note = note
    msg = f"Your appointment with {apt.officer.name} on {apt.date.strftime('%d %b %Y')} was Rejected. {('Reason: ' + note) if note else ''}"
    db.session.add(Notification(user_id=apt.user_id, message=msg))
    db.session.add(AuditLog(admin_id=current_user.id, action='reject',
                             detail=f"#{apt.id} {apt.student_name} → Rejected: {note}"))
    db.session.commit()
    from utils import send_email, rejection_email
    student = db.session.get(User, apt.user_id)
    send_email('Appointment Rejected — IUT', [student.email], rejection_email(apt, student, note))
    flash('Appointment rejected.', 'info')
    return redirect(request.referrer or url_for('officer.dashboard'))

# ── QR scan / check-in ────────────────────────────────────────────────────────
@officer_bp.route('/scan', methods=['GET'])
@login_required
@officer_required
def scan_page():
    return render_template('officer/scan_qr.html')

@officer_bp.route('/checkin', methods=['POST'])
@login_required
@officer_required
def checkin():
    """
    Called when officer scans a QR code.
    QR data format: APT-{appointment_id}-{qr_token}
    """
    qr_data = request.form.get('qr_data', '').strip()
    if not qr_data.startswith('APT-'):
        return jsonify({'success': False, 'error': 'Invalid QR format'}), 400
    parts = qr_data.split('-')
    if len(parts) != 3:
        return jsonify({'success': False, 'error': 'Malformed QR data'}), 400
    try:
        apt_id = int(parts[1])
    except ValueError:
        return jsonify({'success': False, 'error': 'Invalid appointment ID'}), 400

    apt = db.session.get(Appointment, apt_id)
    officer = get_officer_record()

    if not apt:
        return jsonify({'success': False, 'error': 'Appointment not found'}), 404
    if officer and apt.officer_id != officer.id:
        return jsonify({'success': False, 'error': 'This appointment belongs to another officer'}), 403
    if apt.qr_code_data != qr_data:
        return jsonify({'success': False, 'error': 'QR token mismatch — possible forgery'}), 403
    if apt.status == 'Completed':
        return jsonify({'success': False, 'error': 'Appointment already completed'}), 400
    if apt.status not in ('Approved', 'Pending'):
        return jsonify({'success': False, 'error': f'Cannot check in — status is {apt.status}'}), 400

    apt.status = 'Completed'
    msg = f"Check-in verified! Your appointment with {apt.officer.name} has been marked Completed."
    db.session.add(Notification(user_id=apt.user_id, message=msg))
    db.session.add(AuditLog(admin_id=current_user.id, action='qr_checkin',
                             detail=f"#{apt.id} {apt.student_name} checked in by {current_user.name}"))
    db.session.commit()
    return jsonify({'success': True, 'message': f'Check-in confirmed for {apt.student_name}',
                    'appointment': {'id': apt.id, 'student': apt.student_name,
                                    'date': str(apt.date), 'time': apt.time, 'issue': apt.issue}})

# ── My schedule ────────────────────────────────────────────────────────────────
@officer_bp.route('/schedule')
@login_required
@officer_required
def schedule():
    officer = get_officer_record()
    if not officer:
        flash('No officer profile found.', 'warning')
        return redirect(url_for('officer.dashboard'))
    apts = Appointment.query.filter_by(officer_id=officer.id)\
        .filter(Appointment.date >= datetime.now(timezone.utc).date())\
        .order_by(Appointment.date, Appointment.time).all()
    return render_template('officer/schedule.html', officer=officer, appointments=apts)
