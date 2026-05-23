"""
Officer blueprint — for users with role='officer'.
Officers can: view their appointments, approve/reject, scan QR for check-in,
set unavailability, mark as completed, reschedule, edit location, add guests,
mark no-show, report booking, cancel event.
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

def _get_apt_or_abort(apt_id):
    """
    Fetch appointment and verify the current officer owns it.
    Returns (apt, officer) tuple. Flashes + redirects on failure.
    """
    apt = db.session.get(Appointment, apt_id)
    officer = get_officer_record()
    if not apt or (officer and apt.officer_id != officer.id):
        flash('Not authorized.', 'danger')
        return None, None
    return apt, officer

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


# ══════════════════════════════════════════════════════════════════════════════
# NEW APPOINTMENT MANAGEMENT ROUTES
# ══════════════════════════════════════════════════════════════════════════════

# ── Reschedule (officer sets a new date/time directly) ────────────────────────
@officer_bp.route('/reschedule/<int:apt_id>', methods=['POST'])
@login_required
@officer_required
def reschedule(apt_id):
    apt, officer = _get_apt_or_abort(apt_id)
    if not apt:
        return redirect(url_for('officer.dashboard'))

    new_date_str = request.form.get('new_date', '').strip()
    new_time     = request.form.get('new_time', '').strip()
    reason       = request.form.get('reason', '').strip()

    if not new_date_str or not new_time:
        flash('Please provide both a new date and time.', 'warning')
        return redirect(request.referrer or url_for('officer.dashboard'))

    old_date = apt.date.strftime('%d %b %Y')
    old_time = apt.time

    apt.date   = datetime.strptime(new_date_str, '%Y-%m-%d').date()
    apt.time   = new_time
    apt.status = 'Approved'   # keep approved after officer reschedule

    msg = (
        f"Your appointment with {apt.officer.name} has been rescheduled "
        f"from {old_date} {old_time} to "
        f"{apt.date.strftime('%d %b %Y')} {apt.time}."
        + (f" Reason: {reason}" if reason else "")
    )
    db.session.add(Notification(user_id=apt.user_id, message=msg))
    db.session.add(AuditLog(
        admin_id=current_user.id,
        action='reschedule',
        detail=f"#{apt.id} {apt.student_name} → rescheduled to {apt.date} {apt.time}"
    ))
    db.session.commit()

    from utils import send_email
    student = db.session.get(User, apt.user_id)
    body = (
        f"<p>Dear {apt.student_name},</p>"
        f"<p>Your appointment with <strong>{apt.officer.name}</strong> has been rescheduled.</p>"
        f"<ul><li><strong>New date:</strong> {apt.date.strftime('%d %b %Y')}</li>"
        f"<li><strong>New time:</strong> {apt.time}</li></ul>"
        + (f"<p><strong>Reason:</strong> {reason}</p>" if reason else "")
        + "<p>Please update your calendar accordingly.</p>"
    )
    send_email('Appointment Rescheduled — IUT', [student.email], body)

    flash('Appointment rescheduled successfully.', 'success')
    return redirect(request.referrer or url_for('officer.dashboard'))


# ── Request Reschedule (asks student to pick a new slot) ──────────────────────
@officer_bp.route('/request-reschedule/<int:apt_id>', methods=['POST'])
@login_required
@officer_required
def request_reschedule(apt_id):
    apt, officer = _get_apt_or_abort(apt_id)
    if not apt:
        return redirect(url_for('officer.dashboard'))

    message = request.form.get('message', '').strip()

    apt.status = 'Reschedule Requested'

    msg = (
        f"Officer {apt.officer.name} has requested to reschedule your appointment "
        f"on {apt.date.strftime('%d %b %Y')} at {apt.time}. "
        + (f"Message: {message}" if message else "Please log in to choose a new time.")
    )
    db.session.add(Notification(user_id=apt.user_id, message=msg))
    db.session.add(AuditLog(
        admin_id=current_user.id,
        action='request_reschedule',
        detail=f"#{apt.id} {apt.student_name} → reschedule requested"
    ))
    db.session.commit()

    from utils import send_email
    student = db.session.get(User, apt.user_id)
    body = (
        f"<p>Dear {apt.student_name},</p>"
        f"<p><strong>{apt.officer.name}</strong> has requested to reschedule your appointment "
        f"on <strong>{apt.date.strftime('%d %b %Y')} at {apt.time}</strong>.</p>"
        + (f"<p><strong>Message:</strong> {message}</p>" if message else "")
        + "<p>Please log in to the IUT Appointment portal to choose a new time slot.</p>"
    )
    send_email('Reschedule Request — IUT Appointment', [student.email], body)

    flash('Reschedule request sent to the student.', 'info')
    return redirect(request.referrer or url_for('officer.dashboard'))


# ── Edit Location ──────────────────────────────────────────────────────────────
@officer_bp.route('/edit-location/<int:apt_id>', methods=['POST'])
@login_required
@officer_required
def edit_location(apt_id):
    apt, officer = _get_apt_or_abort(apt_id)
    if not apt:
        return redirect(url_for('officer.dashboard'))

    location     = request.form.get('location', '').strip()
    meeting_link = request.form.get('meeting_link', '').strip()

    # Store on the appointment — add these columns to your Appointment model
    # if they don't exist yet (see migration note below).
    apt.location     = location or None
    apt.meeting_link = meeting_link or None

    msg = (
        f"The location for your appointment with {apt.officer.name} on "
        f"{apt.date.strftime('%d %b %Y')} has been updated"
        + (f" to: {location}" if location else "")
        + (f". Join link: {meeting_link}" if meeting_link else "")
        + "."
    )
    db.session.add(Notification(user_id=apt.user_id, message=msg))
    db.session.add(AuditLog(
        admin_id=current_user.id,
        action='edit_location',
        detail=f"#{apt.id} {apt.student_name} → location='{location}' link='{meeting_link}'"
    ))
    db.session.commit()

    from utils import send_email
    student = db.session.get(User, apt.user_id)
    body = (
        f"<p>Dear {apt.student_name},</p>"
        f"<p>The location for your appointment with <strong>{apt.officer.name}</strong> "
        f"on <strong>{apt.date.strftime('%d %b %Y')} at {apt.time}</strong> has been updated.</p>"
        + (f"<p><strong>Location:</strong> {location}</p>" if location else "")
        + (f"<p><strong>Meeting link:</strong> <a href='{meeting_link}'>{meeting_link}</a></p>"
           if meeting_link else "")
    )
    send_email('Appointment Location Updated — IUT', [student.email], body)

    flash('Location updated.', 'success')
    return redirect(request.referrer or url_for('officer.dashboard'))


# ── Add Guests ─────────────────────────────────────────────────────────────────
@officer_bp.route('/add-guests/<int:apt_id>', methods=['POST'])
@login_required
@officer_required
def add_guests(apt_id):
    apt, officer = _get_apt_or_abort(apt_id)
    if not apt:
        return redirect(url_for('officer.dashboard'))

    raw_guests = request.form.get('guests', '').strip()
    guest_note = request.form.get('guest_note', '').strip()

    # Parse + deduplicate the email list
    new_emails = [e.strip() for e in raw_guests.split(',') if e.strip()]
    if not new_emails:
        flash('Please enter at least one guest email.', 'warning')
        return redirect(request.referrer or url_for('officer.dashboard'))

    # Append to existing extra_guests (comma-separated string column)
    existing   = [e.strip() for e in (apt.extra_guests or '').split(',') if e.strip()]
    combined   = list(dict.fromkeys(existing + new_emails))   # preserve order, dedupe
    apt.extra_guests = ', '.join(combined)

    db.session.add(AuditLog(
        admin_id=current_user.id,
        action='add_guests',
        detail=f"#{apt.id} {apt.student_name} → guests added: {', '.join(new_emails)}"
    ))
    db.session.commit()

    from utils import send_email
    invite_body = (
        f"<p>You have been invited to an appointment.</p>"
        f"<ul><li><strong>Officer:</strong> {apt.officer.name}</li>"
        f"<li><strong>Student:</strong> {apt.student_name}</li>"
        f"<li><strong>Date:</strong> {apt.date.strftime('%d %b %Y')}</li>"
        f"<li><strong>Time:</strong> {apt.time}</li>"
        + (f"<li><strong>Location:</strong> {apt.location}</li>" if apt.location else "")
        + "</ul>"
        + (f"<p>{guest_note}</p>" if guest_note else "")
    )
    for email in new_emails:
        send_email('You are invited — IUT Appointment', [email], invite_body)

    flash(f'{len(new_emails)} guest(s) added and notified.', 'success')
    return redirect(request.referrer or url_for('officer.dashboard'))


# ── Mark as No-Show ────────────────────────────────────────────────────────────
@officer_bp.route('/no-show/<int:apt_id>', methods=['POST'])
@login_required
@officer_required
def mark_noshow(apt_id):
    apt, officer = _get_apt_or_abort(apt_id)
    if not apt:
        return redirect(url_for('officer.dashboard'))

    note = request.form.get('note', '').strip()

    apt.status        = 'No-Show'
    apt.rejection_note = note or 'Marked as no-show by officer.'   # reuse existing note column

    msg = (
        f"Your appointment with {apt.officer.name} on "
        f"{apt.date.strftime('%d %b %Y')} at {apt.time} "
        f"was marked as No-Show."
        + (f" Note: {note}" if note else "")
    )
    db.session.add(Notification(user_id=apt.user_id, message=msg))
    db.session.add(AuditLog(
        admin_id=current_user.id,
        action='mark_noshow',
        detail=f"#{apt.id} {apt.student_name} → No-Show"
    ))
    db.session.commit()

    from utils import send_email
    student = db.session.get(User, apt.user_id)
    body = (
        f"<p>Dear {apt.student_name},</p>"
        f"<p>Your appointment with <strong>{apt.officer.name}</strong> on "
        f"<strong>{apt.date.strftime('%d %b %Y')} at {apt.time}</strong> "
        f"has been marked as <strong>No-Show</strong> because you did not attend.</p>"
        + (f"<p><strong>Note:</strong> {note}</p>" if note else "")
        + "<p>Please book a new appointment if you still need assistance.</p>"
    )
    send_email('Appointment No-Show — IUT', [student.email], body)

    flash('Appointment marked as no-show.', 'warning')
    return redirect(request.referrer or url_for('officer.dashboard'))


# ── Report Booking ─────────────────────────────────────────────────────────────
@officer_bp.route('/report/<int:apt_id>', methods=['POST'])
@login_required
@officer_required
def report_booking(apt_id):
    apt, officer = _get_apt_or_abort(apt_id)
    if not apt:
        return redirect(url_for('officer.dashboard'))

    reason  = request.form.get('report_reason', '').strip()
    details = request.form.get('report_details', '').strip()

    # Store report info on the appointment
    apt.is_reported    = True
    apt.report_reason  = reason
    apt.report_details = details

    db.session.add(AuditLog(
        admin_id=current_user.id,
        action='report_booking',
        detail=f"#{apt.id} {apt.student_name} → reported: {reason} | {details}"
    ))
    db.session.commit()

    # Notify all admins
    from models import User as UserModel
    admins = UserModel.query.filter(UserModel.role.in_(['admin', 'super_admin'])).all()
    for admin in admins:
        db.session.add(Notification(
            user_id=admin.id,
            message=(
                f"Officer {current_user.name} reported appointment #{apt.id} "
                f"({apt.student_name}, {apt.date.strftime('%d %b %Y')}). "
                f"Reason: {reason}."
            )
        ))
    db.session.commit()

    flash('Booking reported. The admin team has been notified.', 'info')
    return redirect(request.referrer or url_for('officer.dashboard'))


# ── Cancel Event ───────────────────────────────────────────────────────────────
@officer_bp.route('/cancel/<int:apt_id>', methods=['POST'])
@login_required
@officer_required
def cancel_appointment(apt_id):
    apt, officer = _get_apt_or_abort(apt_id)
    if not apt:
        return redirect(url_for('officer.dashboard'))

    reason = request.form.get('cancel_reason', '').strip()

    apt.status        = 'Cancelled'
    apt.rejection_note = reason or 'Cancelled by officer.'

    msg = (
        f"Your appointment with {apt.officer.name} on "
        f"{apt.date.strftime('%d %b %Y')} at {apt.time} has been Cancelled."
        + (f" Reason: {reason}" if reason else "")
    )
    db.session.add(Notification(user_id=apt.user_id, message=msg))
    db.session.add(AuditLog(
        admin_id=current_user.id,
        action='cancel_appointment',
        detail=f"#{apt.id} {apt.student_name} → Cancelled: {reason}"
    ))
    db.session.commit()

    from utils import send_email, rejection_email
    student = db.session.get(User, apt.user_id)
    body = (
        f"<p>Dear {apt.student_name},</p>"
        f"<p>Your appointment with <strong>{apt.officer.name}</strong> on "
        f"<strong>{apt.date.strftime('%d %b %Y')} at {apt.time}</strong> "
        f"has been <strong>cancelled</strong>.</p>"
        + (f"<p><strong>Reason:</strong> {reason}</p>" if reason else "")
        + "<p>You may book a new appointment if needed.</p>"
    )
    send_email('Appointment Cancelled — IUT', [student.email], body)

    flash('Appointment cancelled.', 'danger')
    return redirect(request.referrer or url_for('officer.dashboard'))
