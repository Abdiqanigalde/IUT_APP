from flask import Blueprint, render_template, redirect, url_for, flash, request, Response, jsonify
from flask_login import login_required, current_user
from models import db, Appointment, User, Officer, Notification, OfficerUnavailability, AuditLog, OfficerWorkingHours
from forms import OfficerForm, UnavailabilityForm, WorkingHoursForm, RejectNoteForm, OfficerProfileForm
from datetime import datetime, timedelta, timezone
import csv, io
from flask_bcrypt import Bcrypt as _Bcrypt
_bcrypt_admin = _Bcrypt()

admin_bp = Blueprint('admin', __name__)

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if current_user.role not in ('admin', 'super_admin'):
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated

def log_action(action, detail):
    db.session.add(AuditLog(admin_id=current_user.id, action=action, detail=detail))

# ── Dashboard ─────────────────────────────────────────────────────────────────
@admin_bp.route('/admin/dashboard')
@login_required
@admin_required
def dashboard():
    today = datetime.now(timezone.utc).date()

    # ── Summary counts ────────────────────────────────────────────────────────
    total     = Appointment.query.count()
    pending   = Appointment.query.filter_by(status='Pending').count()
    approved  = Appointment.query.filter_by(status='Approved').count()
    completed = Appointment.query.filter_by(status='Completed').count()
    rejected  = Appointment.query.filter_by(status='Rejected').count()
    cancelled = Appointment.query.filter_by(status='Cancelled').count()

    total_students  = User.query.filter_by(role='student').count()
    active_students = User.query.filter_by(role='student', is_active=True).count()

    # ── Today schedule ────────────────────────────────────────────────────────
    today_schedule = Appointment.query.filter_by(date=today).order_by(Appointment.time).all()

    # ── Last 7 days trend ─────────────────────────────────────────────────────
    weekly = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        cnt = Appointment.query.filter(Appointment.date == d).count()
        weekly.append({'date': d.strftime('%a %d'), 'count': cnt})

    # ── Full-year monthly data ────────────────────────────────────────────────
    months_data = []
    for m in range(1, 13):
        cnt = Appointment.query.filter(
            db.extract('month', Appointment.date) == m,
            db.extract('year',  Appointment.date) == today.year
        ).count()
        months_data.append({'label': datetime(today.year, m, 1).strftime('%b'), 'count': cnt})

    # ── Officer breakdown ─────────────────────────────────────────────────────
    all_officers = Officer.query.all()
    officer_names  = [o.name for o in all_officers]
    officer_counts = [Appointment.query.filter_by(officer_id=o.id).count() for o in all_officers]
    officer_stats  = []
    for o in all_officers:
        tot  = Appointment.query.filter_by(officer_id=o.id).count()
        appr = Appointment.query.filter_by(officer_id=o.id, status='Approved').count()
        comp = Appointment.query.filter_by(officer_id=o.id, status='Completed').count()
        rej  = Appointment.query.filter_by(officer_id=o.id, status='Rejected').count()
        officer_stats.append({'name': o.name, 'total': tot, 'approved': appr,
                               'completed': comp, 'rejected': rej})

    status_counts = {'Pending': pending, 'Approved': approved,
                     'Completed': completed, 'Rejected': rejected, 'Cancelled': cancelled}

    return render_template('admin/dashboard.html',
        total=total, pending=pending, approved=approved,
        completed=completed, rejected=rejected, cancelled=cancelled,
        total_students=total_students, active_students=active_students,
        today_schedule=today_schedule,
        officers=officer_names, officer_counts=officer_counts,
        officer_stats=officer_stats, status_counts=status_counts,
        weekly=weekly, months_data=months_data, year=today.year)

# ── Appointments ──────────────────────────────────────────────────────────────
@admin_bp.route('/admin/appointments', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_appointments():
    officer_filter = request.args.get('officer', '')
    status_filter = request.args.get('status', '')
    date_filter = request.args.get('date', '')

    query = Appointment.query.join(Officer)
    if officer_filter:
        query = query.filter(Officer.name == officer_filter)
    if status_filter:
        query = query.filter(Appointment.status == status_filter)
    if date_filter:
        try:
            query = query.filter(Appointment.date == datetime.strptime(date_filter, '%Y-%m-%d').date())
        except ValueError:
            pass

    appointments = query.order_by(Appointment.date.desc(), Appointment.time.desc()).all()
    all_officers = Officer.query.all()

    # Bulk action
    if request.method == 'POST':
        ids = request.form.getlist('selected_ids')
        action = request.form.get('bulk_action')
        if ids and action in ['Approved', 'Rejected']:
            for aid in ids:
                apt = db.session.get(Appointment, int(aid))
                if apt and apt.status == 'Pending':
                    apt.status = action
                    msg = f"Your appointment with {apt.officer.name} on {apt.date.strftime('%d %b %Y')} has been {action}."
                    db.session.add(Notification(user_id=apt.user_id, message=msg))
                    student = db.session.get(User, apt.user_id)
                    from utils import send_email, appointment_status_email
                    send_email(f"Appointment {action} — IUT", [student.email], appointment_status_email(apt, action))
            log_action(f'bulk_{action.lower()}', f"Bulk {action} on {len(ids)} appointment(s)")
            db.session.commit()
            flash(f'{len(ids)} appointment(s) {action.lower()}.', 'success')
        return redirect(url_for('admin.manage_appointments',
                                officer=officer_filter, status=status_filter, date=date_filter))

    return render_template('admin/appointments.html', appointments=appointments,
                           all_officers=all_officers,
                           officer_filter=officer_filter, status_filter=status_filter, date_filter=date_filter)

@admin_bp.route('/admin/update_status/<int:appointment_id>/<string:status>', methods=['GET', 'POST'])
@login_required
@admin_required
def update_status(appointment_id, status):
    apt = db.session.get(Appointment, appointment_id)
    if not apt:
        return redirect(url_for('admin.manage_appointments'))

    # Rejection requires a note — show modal/form
    if status == 'Rejected':
        form = RejectNoteForm()
        if form.validate_on_submit():
            apt.status = 'Rejected'
            apt.rejection_note = form.rejection_note.data
            msg = f"Your appointment with {apt.officer.name} on {apt.date.strftime('%d %b %Y')} was rejected. Reason: {form.rejection_note.data}"
            db.session.add(Notification(user_id=apt.user_id, message=msg))
            student = db.session.get(User, apt.user_id)
            from utils import send_email, rejection_email
            send_email("Appointment Rejected — IUT", [student.email],
                       rejection_email(apt, student, form.rejection_note.data))
            from routes.student import _promote_waitlist
            _promote_waitlist(apt)
            log_action('appointment_rejected',
                       f"#{apt.id} ({apt.student_name} with {apt.officer.name} on {apt.date}) — {form.rejection_note.data}")
            db.session.commit()
            flash('Appointment rejected with note.', 'info')
            return redirect(url_for('admin.manage_appointments'))
        return render_template('admin/reject_modal.html', form=form, apt=apt)

    if status in ['Approved', 'Completed']:
        apt.status = status
        msg = f"Your appointment with {apt.officer.name} on {apt.date.strftime('%d %b %Y')} at {apt.time} has been {status}."
        db.session.add(Notification(user_id=apt.user_id, message=msg))
        student = db.session.get(User, apt.user_id)

        # Add timeline event
        from models import AppointmentTimeline
        db.session.add(AppointmentTimeline(appointment_id=apt.id, status=status,
                                           note=f"Status set to {status} by admin."))

        if status == 'Approved':
            # Generate real QR code if not already set
            if not apt.qr_code_data:
                import secrets as _s
                from app import generate_qr_data
                qr_data, _ = generate_qr_data(apt.id, _s.token_urlsafe(16))
                apt.qr_code_data = qr_data

            # Send QR ticket email
            from app import generate_qr_data as _gqr
            _, qr_b64 = _gqr(apt.id, apt.qr_code_data.split('-')[2] if apt.qr_code_data else 'x')
            from utils import send_email, qr_appointment_email
            send_email(f"Appointment Approved + QR Ticket — IUT", [student.email],
                       qr_appointment_email(apt, student, qr_b64))
        else:
            from utils import send_email, appointment_status_email
            send_email(f"Appointment {status} — IUT", [student.email], appointment_status_email(apt, status))

        log_action(f'appointment_{status.lower()}',
                   f"#{apt.id} ({apt.student_name} with {apt.officer.name} on {apt.date}) → {status}")
        db.session.commit()

        # Real-time socket push
        try:
            from app import push_status_update
            push_status_update(apt.user_id, apt.id, status, msg)
        except Exception:
            pass

        flash(f'Appointment marked as {status}.', 'success')
    return redirect(request.referrer or url_for('admin.manage_appointments'))

# ── Student management ────────────────────────────────────────────────────────
@admin_bp.route('/admin/students')
@login_required
@admin_required
def manage_students():
    search = request.args.get('search', '').strip()
    dept = request.args.get('department', '').strip()
    status = request.args.get('status', '').strip()

    query = User.query.filter_by(role='student')
    if search:
        query = query.filter(
            db.or_(User.name.ilike(f'%{search}%'),
                   User.email.ilike(f'%{search}%'),
                   User.student_id_num.ilike(f'%{search}%')))
    if dept:
        query = query.filter(User.department.ilike(f'%{dept}%'))
    if status == 'active':
        query = query.filter_by(is_active=True)
    elif status == 'inactive':
        query = query.filter_by(is_active=False)

    students = query.order_by(User.created_at.desc()).all()
    departments = db.session.query(User.department).filter(User.role=='student', User.department != None).distinct().all()
    departments = [d[0] for d in departments if d[0]]

    return render_template('admin/students.html', students=students,
                           search=search, dept=dept, status_filter=status,
                           departments=departments)

@admin_bp.route('/admin/student/<int:user_id>/toggle')
@login_required
@admin_required
def toggle_student(user_id):
    user = db.session.get(User, user_id)
    if user and user.role == 'student':
        user.is_active = not user.is_active
        action = 'activated' if user.is_active else 'deactivated'
        log_action(f'student_{action}', f"Student {user.name} ({user.email}) {action}")
        db.session.commit()
        flash(f'Student account {action}.', 'success')
    return redirect(url_for('admin.manage_students'))

@admin_bp.route('/admin/student/<int:user_id>')
@login_required
@admin_required
def student_detail(user_id):
    student = db.session.get(User, user_id)
    if not student or student.role != 'student':
        from flask import abort; abort(404)
    appointments = Appointment.query.filter_by(user_id=user_id).order_by(Appointment.date.desc()).all()
    return render_template('admin/student_detail.html', student=student, appointments=appointments)

# ── Officers ──────────────────────────────────────────────────────────────────
@admin_bp.route('/admin/officers', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_officers():
    form = OfficerProfileForm()
    if form.validate_on_submit():
        # Check if login email is already taken
        if User.query.filter_by(email=form.login_email.data).first():
            flash('Login email already in use. Choose a different one.', 'danger')
        else:
            off_days = ','.join(form.recurring_off_days.data) if form.recurring_off_days.data else ''
            # Create user account for officer login
            hashed_pw = _bcrypt_admin.generate_password_hash(form.login_password.data).decode('utf-8')
            user = User(
                name=form.name.data,
                email=form.login_email.data,
                password=hashed_pw,
                role='officer',
                is_active=True,
                email_verified=True
            )
            db.session.add(user)
            db.session.flush()  # get user.id before commit
            officer = Officer(
                name=form.name.data, designation=form.designation.data,
                bio=form.bio.data, handles=form.handles.data,
                email=form.login_email.data, room=form.room.data,
                photo_url=form.photo_url.data if form.photo_url.data else None,
                work_start=form.work_start.data, work_end=form.work_end.data,
                daily_limit=form.daily_limit.data, recurring_off_days=off_days
            )
            db.session.add(officer)
            db.session.commit()
            log_action('officer_added', f"Added {officer.name} ({officer.designation}) with login {form.login_email.data}")
            flash(f'Officer added! Login: {form.login_email.data} / Password: {form.login_password.data}', 'success')
            return redirect(url_for('admin.manage_officers'))
    officers = Officer.query.all()
    today = datetime.now(timezone.utc).date()
    return render_template('admin/officers.html', officers=officers, form=form, today=today)

@admin_bp.route('/admin/officer/delete/<int:officer_id>')
@login_required
@admin_required
def delete_officer(officer_id):
    officer = db.session.get(Officer, officer_id)
    if not officer:
        flash('Officer not found.', 'danger')
        return redirect(url_for('admin.manage_officers'))
    # Also delete linked user account
    linked_user = User.query.filter_by(email=officer.email, role='officer').first()
    log_action('officer_deleted', f"Deleted {officer.name}")
    db.session.delete(officer)
    if linked_user:
        db.session.delete(linked_user)
    db.session.commit()
    flash('Officer and login account removed.', 'info')
    return redirect(url_for('admin.manage_officers'))

# ── Working hours ─────────────────────────────────────────────────────────────
@admin_bp.route('/admin/officer/<int:officer_id>/hours', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_hours(officer_id):
    officer = db.session.get(Officer, officer_id)
    form = WorkingHoursForm()
    if form.validate_on_submit():
        existing = OfficerWorkingHours.query.filter_by(officer_id=officer_id, weekday=form.weekday.data).first()
        if existing:
            existing.start_time = form.start_time.data
            existing.end_time = form.end_time.data
        else:
            db.session.add(OfficerWorkingHours(officer_id=officer_id, weekday=form.weekday.data,
                start_time=form.start_time.data, end_time=form.end_time.data))
        db.session.commit()
        flash('Working hours saved!', 'success')
        return redirect(url_for('admin.manage_hours', officer_id=officer_id))
    hours = {wh.weekday: wh for wh in officer.working_hours}
    days = ['Monday','Tuesday','Wednesday','Thursday','Friday']
    return render_template('admin/working_hours.html', officer=officer, form=form, hours=hours, days=days)

@admin_bp.route('/admin/officer/hours/delete/<int:hours_id>')
@login_required
@admin_required
def delete_hours(hours_id):
    wh = db.session.get(OfficerWorkingHours, hours_id)
    if not wh:
        flash('Working hours record not found.', 'danger')
        return redirect(url_for('admin.manage_officers'))
    oid = wh.officer_id
    db.session.delete(wh)
    db.session.commit()
    flash('Override removed.', 'info')
    return redirect(url_for('admin.manage_hours', officer_id=oid))

# ── Unavailability ────────────────────────────────────────────────────────────
@admin_bp.route('/admin/officer/<int:officer_id>/unavailability', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_unavailability(officer_id):
    officer = db.session.get(Officer, officer_id)
    form = UnavailabilityForm()
    if form.validate_on_submit():
        if form.end_date.data < form.start_date.data:
            flash('End date cannot be before start date.', 'danger')
        else:
            u = OfficerUnavailability(officer_id=officer.id, start_date=form.start_date.data,
                                      end_date=form.end_date.data, reason=form.reason.data)
            db.session.add(u)
            db.session.commit()
            affected = Appointment.query.filter(
                Appointment.officer_id == officer.id,
                Appointment.date >= form.start_date.data,
                Appointment.date <= form.end_date.data,
                Appointment.status.in_(['Pending', 'Approved'])
            ).all()
            for apt in affected:
                apt.status = 'Rejected'
                apt.rejection_note = form.reason.data
                db.session.add(Notification(user_id=apt.user_id,
                    message=f"Your appointment with {officer.name} on {apt.date} was cancelled: {form.reason.data}"))
                student = db.session.get(User, apt.user_id)
                from utils import send_email, rejection_email
                send_email("Appointment Cancelled — IUT", [student.email],
                           rejection_email(apt, student, form.reason.data))
            log_action('unavailability_added',
                f"{officer.name} unavailable {form.start_date.data}–{form.end_date.data}: {form.reason.data}")
            db.session.commit()
            flash(f'Unavailability added. {len(affected)} appointment(s) cancelled.', 'success')
            return redirect(url_for('admin.manage_unavailability', officer_id=officer.id))
    periods = OfficerUnavailability.query.filter_by(officer_id=officer.id)\
        .order_by(OfficerUnavailability.start_date).all()
    today = datetime.now(timezone.utc).date()
    return render_template('admin/unavailability.html', officer=officer, form=form, periods=periods, today=today)

@admin_bp.route('/admin/unavailability/delete/<int:period_id>')
@login_required
@admin_required
def delete_unavailability(period_id):
    period = db.session.get(OfficerUnavailability, period_id)
    if not period:
        flash('Unavailability record not found.', 'danger')
        return redirect(url_for('admin.manage_officers'))
    oid = period.officer_id
    db.session.delete(period)
    db.session.commit()
    flash('Unavailability removed.', 'success')
    return redirect(url_for('admin.manage_unavailability', officer_id=oid))

# ── Send reminders (call this via a cron job or manually) ─────────────────────
@admin_bp.route('/admin/send-reminders')
@login_required
@admin_required
def send_reminders():
    from utils import send_email, reminder_email
    tomorrow = datetime.now(timezone.utc).date() + timedelta(days=1)
    apts = Appointment.query.filter_by(date=tomorrow, status='Approved', reminder_sent=False).all()
    sent = 0
    for apt in apts:
        student = db.session.get(User, apt.user_id)
        send_email("Appointment Reminder — Tomorrow — IUT", [student.email], reminder_email(apt, student))
        db.session.add(Notification(user_id=apt.user_id,
            message=f"Reminder: Your appointment with {apt.officer.name} is tomorrow at {apt.time}."))
        apt.reminder_sent = True
        sent += 1
    db.session.commit()
    flash(f'Reminders sent to {sent} student(s).', 'success')
    return redirect(url_for('admin.dashboard'))

# ── Audit log ─────────────────────────────────────────────────────────────────
@admin_bp.route('/admin/audit')
@login_required
@admin_required
def audit_log():
    logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(200).all()
    return render_template('admin/audit_log.html', logs=logs)


# ── Export CSV ────────────────────────────────────────────────────────────────
@admin_bp.route('/admin/export/csv')
@login_required
@admin_required
def export_csv():
    appointments = Appointment.query.all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID','Student Name','Student ID','Department','Officer','Date','Time','Status','Rejection Note'])
    for apt in appointments:
        writer.writerow([apt.id, apt.student_name, apt.student_id_num, apt.department,
                         apt.officer.name, apt.date, apt.time, apt.status, apt.rejection_note or ''])
    output.seek(0)
    return Response(output, mimetype="text/csv",
                    headers={"Content-disposition": "attachment; filename=appointments_export.csv"})

# ── Profile ───────────────────────────────────────────────────────────────────
from forms import ProfileForm
from flask_bcrypt import Bcrypt as _Bcrypt
_bcrypt = _Bcrypt()

@admin_bp.route('/admin/profile', methods=['GET', 'POST'])
@login_required
@admin_required
def profile():
    form = ProfileForm()
    if form.validate_on_submit():
        if form.email.data != current_user.email:
            if User.query.filter_by(email=form.email.data).first():
                flash('Email already in use.', 'danger')
                return render_template('profile.html', form=form)
        current_user.name = form.name.data
        current_user.email = form.email.data
        if form.new_password.data:
            if not _bcrypt.check_password_hash(current_user.password, form.current_password.data):
                flash('Current password incorrect.', 'danger')
                return render_template('profile.html', form=form)
            current_user.password = _bcrypt.generate_password_hash(form.new_password.data).decode('utf-8')
        db.session.commit()
        flash('Profile updated!', 'success')
        return redirect(url_for('admin.profile'))
    elif request.method == 'GET':
        form.name.data = current_user.name
        form.email.data = current_user.email
    return render_template('profile.html', form=form)
