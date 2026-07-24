from flask import Blueprint, render_template, redirect, url_for, flash, request, Response, jsonify
from flask_login import login_required, current_user
from models import db, Appointment, User, Officer, Office, Notification, OfficerUnavailability, AuditLog, OfficerWorkingHours, GlobalHoliday
from forms import OfficerForm, UnavailabilityForm, WorkingHoursForm, RejectNoteForm, OfficerProfileForm, OfficeForm
from routes.visa import upload_to_cloudinary
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
    from sqlalchemy import func, case
    today = datetime.now(timezone.utc).date()

    # Status counts — was 6 separate COUNT() queries, now 1 grouped query.
    status_rows = db.session.query(Appointment.status, func.count(Appointment.id))\
        .group_by(Appointment.status).all()
    status_map = {status: cnt for status, cnt in status_rows}
    total     = sum(status_map.values())
    pending   = status_map.get('Pending', 0)
    approved  = status_map.get('Approved', 0)
    completed = status_map.get('Completed', 0)
    rejected  = status_map.get('Rejected', 0)
    cancelled = status_map.get('Cancelled', 0)

    total_students  = User.query.filter_by(role='student').count()
    active_students = User.query.filter_by(role='student', is_active=True).count()

    today_schedule = Appointment.query.filter_by(date=today).order_by(Appointment.time).all()

    # Last 7 days — was 7 separate COUNT() queries, now 1 grouped query.
    week_start = today - timedelta(days=6)
    daily_rows = db.session.query(Appointment.date, func.count(Appointment.id))\
        .filter(Appointment.date >= week_start, Appointment.date <= today)\
        .group_by(Appointment.date).all()
    daily_map = {d: cnt for d, cnt in daily_rows}
    weekly = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        weekly.append({'date': d.strftime('%a %d'), 'count': daily_map.get(d, 0)})

    # This year, by month — was 12 separate COUNT() queries, now 1 grouped query.
    month_rows = db.session.query(
        func.extract('month', Appointment.date),
        func.count(Appointment.id)
    ).filter(func.extract('year', Appointment.date) == today.year)\
     .group_by(func.extract('month', Appointment.date)).all()
    month_map = {int(m): cnt for m, cnt in month_rows}
    months_data = []
    for m in range(1, 13):
        months_data.append({'label': datetime(today.year, m, 1).strftime('%b'), 'count': month_map.get(m, 0)})

    # Per-officer stats — was up to 4×N separate COUNT() queries, now 1 grouped query.
    all_officers = Officer.query.all()
    officer_names = [o.name for o in all_officers]

    officer_rows = db.session.query(
        Appointment.officer_id,
        func.count(Appointment.id),
        func.sum(case((Appointment.status == 'Approved', 1), else_=0)),
        func.sum(case((Appointment.status == 'Completed', 1), else_=0)),
        func.sum(case((Appointment.status == 'Rejected', 1), else_=0)),
        func.sum(case((Appointment.status == 'Pending', 1), else_=0)),
    ).group_by(Appointment.officer_id).all()
    officer_stat_map = {
        oid: {'total': tot, 'approved': appr or 0, 'completed': comp or 0,
              'rejected': rej or 0, 'pending': pend or 0}
        for oid, tot, appr, comp, rej, pend in officer_rows
    }

    # Today's approved/pending load per officer, to measure capacity utilization
    # against each officer's daily_limit (0 = unlimited).
    today_rows = db.session.query(
        Appointment.officer_id, func.count(Appointment.id)
    ).filter(
        Appointment.date == today,
        Appointment.status.in_(['Pending', 'Approved'])
    ).group_by(Appointment.officer_id).all()
    today_map = {oid: cnt for oid, cnt in today_rows}

    officer_counts  = []
    officer_stats   = []
    for o in all_officers:
        s = officer_stat_map.get(o.id, {'total': 0, 'approved': 0, 'completed': 0, 'rejected': 0, 'pending': 0})
        today_load = today_map.get(o.id, 0)

        if o.daily_limit and o.daily_limit > 0:
            utilization = round((today_load / o.daily_limit) * 100)
        else:
            utilization = None  # unlimited capacity — utilization isn't meaningful

        if s['pending'] >= 10 or (utilization is not None and utilization >= 90):
            workload = 'overloaded'
        elif s['pending'] == 0 and s['total'] == 0:
            workload = 'idle'
        elif s['pending'] <= 2 and (utilization is None or utilization < 50):
            workload = 'light'
        else:
            workload = 'balanced'

        officer_counts.append(s['total'])
        officer_stats.append({
            'name': o.name, 'total': s['total'], 'approved': s['approved'],
            'completed': s['completed'], 'rejected': s['rejected'], 'pending': s['pending'],
            'today_load': today_load, 'daily_limit': o.daily_limit or 0,
            'utilization': utilization, 'workload': workload,
        })

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
    status_filter  = request.args.get('status', '')
    date_filter    = request.args.get('date', '')

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

    if request.method == 'POST':
        ids    = request.form.getlist('selected_ids')
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

        from models import AppointmentTimeline
        db.session.add(AppointmentTimeline(appointment_id=apt.id, status=status,
                                           note=f"Status set to {status} by admin."))

        if status == 'Approved':
            if not apt.qr_code_data:
                import secrets as _s
                from app import generate_qr_data
                qr_data, _ = generate_qr_data(apt.id, _s.token_urlsafe(16))
                apt.qr_code_data = qr_data
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
    dept   = request.args.get('department', '').strip()
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

    students    = query.order_by(User.created_at.desc()).all()
    departments = db.session.query(User.department).filter(User.role == 'student', User.department != None).distinct().all()
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
    offices = Office.query.order_by(Office.sort_order, Office.name).all()
    form.office.choices = [(0, '— No office / unassigned —')] + [
        (o.id, o.name if o.is_active else f'{o.name} (inactive)') for o in offices
    ]

    if form.validate_on_submit():
        if User.query.filter_by(email=form.login_email.data).first():
            flash('Login email already in use. Choose a different one.', 'danger')
        else:
            off_days  = ','.join(form.recurring_off_days.data) if form.recurring_off_days.data else ''
            hashed_pw = _bcrypt_admin.generate_password_hash(form.login_password.data).decode('utf-8')
            user = User(
                name=form.name.data, email=form.login_email.data,
                password=hashed_pw, role='officer',
                is_active=True, email_verified=True
            )
            db.session.add(user)
            db.session.flush()

            assigned_office_id = form.office.data if form.office.data else None

            photo_final_url = form.photo_url.data if form.photo_url.data else None
            if form.photo.data and getattr(form.photo.data, 'filename', ''):
                uploaded_url = upload_to_cloudinary(
                    form.photo.data, 'officers', f'officer_new_{int(datetime.now(timezone.utc).timestamp())}'
                )
                if uploaded_url:
                    photo_final_url = uploaded_url
                else:
                    flash('Photo upload failed — check the file type (jpg/jpeg/png/webp). Officer was still saved.', 'warning')

            officer = Officer(
                name=form.name.data, designation=form.designation.data,
                office_id=assigned_office_id,
                bio=form.bio.data, handles=form.handles.data,
                email=form.login_email.data, room=form.room.data,
                photo_url=photo_final_url,
                work_start=form.work_start.data, work_end=form.work_end.data,
                daily_limit=form.daily_limit.data, recurring_off_days=off_days
            )
            db.session.add(officer)

            office_note = ' (no office assigned)'
            if assigned_office_id:
                office = db.session.get(Office, assigned_office_id)
                if office:
                    if not office.is_active:
                        office.is_active = True
                    office_note = f' under "{office.name}"'

            db.session.commit()
            log_action('officer_added', f"Added {officer.name} ({officer.designation}) with login {form.login_email.data}")
            flash(f'Officer added{office_note}! Login: {form.login_email.data} / Password: {form.login_password.data}', 'success')
            return redirect(url_for('admin.manage_officers'))

    officers = Officer.query.all()
    today    = datetime.now(timezone.utc).date()
    return render_template('admin/officers.html', officers=officers, form=form, today=today, offices=offices)


@admin_bp.route('/admin/officer/delete/<int:officer_id>')
@login_required
@admin_required
def delete_officer(officer_id):
    officer = db.session.get(Officer, officer_id)
    if not officer:
        flash('Officer not found.', 'danger')
        return redirect(url_for('admin.manage_officers'))

    appointments = Appointment.query.filter_by(officer_id=officer_id).all()
    for apt in appointments:
        apt.status     = 'Cancelled'
        apt.officer_id = None
        apt.rejection_note = f'Officer {officer.name} was removed from the system.'
        db.session.add(Notification(
            user_id=apt.user_id,
            message=f'Your appointment with {officer.name} on '
                    f'{apt.date.strftime("%d %b %Y")} was cancelled '
                    f'because the officer was removed.'
        ))

    linked_user = User.query.filter_by(email=officer.email, role='officer').first()
    log_action('officer_deleted', f'Deleted {officer.name} — {len(appointments)} appointment(s) cancelled')
    db.session.delete(officer)
    if linked_user:
        db.session.delete(linked_user)
    db.session.commit()
    flash(f'Officer removed successfully. {len(appointments)} appointment(s) cancelled.', 'success')
    return redirect(url_for('admin.manage_officers'))


@admin_bp.route('/admin/officers/<int:officer_id>/edit', methods=['POST'])
@login_required
@admin_required
def edit_officer(officer_id):
    officer = db.session.get(Officer, officer_id)
    if not officer:
        flash('Officer not found.', 'danger')
        return redirect(url_for('admin.manage_officers'))

    officer.name        = request.form.get('edit_name',        officer.name).strip()
    officer.designation = request.form.get('edit_designation', officer.designation).strip()
    edit_office_id       = request.form.get('edit_office_id', '')
    officer.office_id    = int(edit_office_id) if edit_office_id and edit_office_id != '0' else None
    officer.handles     = request.form.get('edit_handles',     officer.handles or '').strip()
    officer.room        = request.form.get('edit_room',        officer.room or '').strip()

    edit_photo_url_text = request.form.get('edit_photo_url', '').strip()
    edit_photo_file      = request.files.get('edit_photo_file')
    if edit_photo_file and edit_photo_file.filename:
        uploaded_url = upload_to_cloudinary(
            edit_photo_file, 'officers', f'officer_{officer.id}_{int(datetime.now(timezone.utc).timestamp())}'
        )
        if uploaded_url:
            officer.photo_url = uploaded_url
        else:
            flash('Photo upload failed — check the file type (jpg/jpeg/png/webp). Other changes were still saved.', 'warning')
    elif edit_photo_url_text:
        officer.photo_url = edit_photo_url_text

    officer.work_start  = request.form.get('edit_work_start',  officer.work_start or '08:00').strip()
    officer.work_end    = request.form.get('edit_work_end',    officer.work_end or '17:00').strip()
    officer.daily_limit = int(request.form.get('edit_daily_limit', officer.daily_limit or 0))
    officer.is_active   = request.form.get('edit_is_active', '1') == '1'

    office_note = ' (no office assigned)'
    if officer.office_id:
        office = db.session.get(Office, officer.office_id)
        if office:
            if not office.is_active:
                office.is_active = True
            office_note = f' under "{office.name}"'

    db.session.commit()
    log_action('officer_updated', f"Updated officer profile: {officer.name}")
    flash(f'{officer.name} updated successfully{office_note}.', 'success')
    return redirect(url_for('admin.manage_officers'))

# ── Offices ───────────────────────────────────────────────────────────────────
@admin_bp.route('/admin/offices', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_offices():
    form = OfficeForm()
    if form.validate_on_submit():
        base_slug = form.name.data.strip().lower().replace(' ', '-')
        base_slug = ''.join(ch for ch in base_slug if ch.isalnum() or ch == '-')
        slug = base_slug
        n = 1
        while Office.query.filter_by(slug=slug).first():
            n += 1
            slug = f'{base_slug}-{n}'

        office = Office(
            name=form.name.data.strip(), slug=slug,
            description=form.description.data,
            icon=form.icon.data or 'fa-building',
            sort_order=form.sort_order.data or 0,
            is_active=True
        )
        db.session.add(office)
        db.session.commit()
        log_action('office_added', f"Added office '{office.name}'")
        flash(f'Office "{office.name}" created.', 'success')
        return redirect(url_for('admin.manage_offices'))

    offices = Office.query.order_by(Office.sort_order, Office.name).all()
    return render_template('admin/offices.html', offices=offices, form=form)


@admin_bp.route('/admin/offices/<int:office_id>/edit', methods=['POST'])
@login_required
@admin_required
def edit_office(office_id):
    office = db.session.get(Office, office_id)
    if not office:
        flash('Office not found.', 'danger')
        return redirect(url_for('admin.manage_offices'))

    office.name        = request.form.get('edit_office_name', office.name).strip()
    office.description = request.form.get('edit_office_description', office.description or '').strip()
    office.icon        = request.form.get('edit_office_icon', office.icon or 'fa-building').strip() or 'fa-building'
    office.sort_order  = int(request.form.get('edit_office_sort_order', office.sort_order or 0))
    office.is_active   = request.form.get('edit_office_is_active', '1') == '1'

    db.session.commit()
    log_action('office_updated', f"Updated office: {office.name}")
    flash(f'{office.name} updated successfully.', 'success')
    return redirect(url_for('admin.manage_offices'))


@admin_bp.route('/admin/offices/<int:office_id>/delete')
@login_required
@admin_required
def delete_office(office_id):
    office = db.session.get(Office, office_id)
    if not office:
        flash('Office not found.', 'danger')
        return redirect(url_for('admin.manage_offices'))

    officer_count = Officer.query.filter_by(office_id=office_id).count()
    for off in Officer.query.filter_by(office_id=office_id).all():
        off.office_id = None

    log_action('office_deleted', f"Deleted office '{office.name}' — {officer_count} officer(s) unassigned")
    db.session.delete(office)
    db.session.commit()
    flash(f'Office removed. {officer_count} officer(s) are now unassigned (not deleted).', 'success')
    return redirect(url_for('admin.manage_offices'))


# ── Working hours ─────────────────────────────────────────────────────────────
@admin_bp.route('/admin/officer/<int:officer_id>/hours', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_hours(officer_id):
    officer = db.session.get(Officer, officer_id)
    form    = WorkingHoursForm()
    if form.validate_on_submit():
        existing = OfficerWorkingHours.query.filter_by(officer_id=officer_id, weekday=form.weekday.data).first()
        if existing:
            existing.start_time = form.start_time.data
            existing.end_time   = form.end_time.data
        else:
            db.session.add(OfficerWorkingHours(officer_id=officer_id, weekday=form.weekday.data,
                start_time=form.start_time.data, end_time=form.end_time.data))
        db.session.commit()
        flash('Working hours saved!', 'success')
        return redirect(url_for('admin.manage_hours', officer_id=officer_id))
    hours = {wh.weekday: wh for wh in officer.working_hours}
    days  = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
    return render_template('admin/working_hours.html', officer=officer, form=form, hours=hours, days=days)

# ── Unavailability ────────────────────────────────────────────────────────────
@admin_bp.route('/admin/officer/<int:officer_id>/unavailability', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_unavailability(officer_id):
    officer = db.session.get(Officer, officer_id)
    form    = UnavailabilityForm()
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
                apt.status         = 'Rejected'
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

# ── Send reminders ────────────────────────────────────────────────────────────
@admin_bp.route('/admin/send-reminders')
@login_required
@admin_required
def send_reminders():
    from utils import send_email, reminder_email
    tomorrow = datetime.now(timezone.utc).date() + timedelta(days=1)
    apts     = Appointment.query.filter_by(date=tomorrow, status='Approved', reminder_sent=False).all()
    sent     = 0
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
    output       = io.StringIO()
    writer       = csv.writer(output)
    writer.writerow(['ID', 'Student Name', 'Student ID', 'Department', 'Officer',
                     'Date', 'Time', 'Status', 'Rejection Note'])
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
        current_user.name  = form.name.data
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
        form.name.data  = current_user.name
        form.email.data = current_user.email
    return render_template('profile.html', form=form)

# ── Global Holidays ───────────────────────────────────────────────────────────
@admin_bp.route('/admin/holidays', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_holidays():
    if request.method == 'POST':
        title     = request.form.get('title', '').strip()
        start_str = request.form.get('start_date', '').strip()
        end_str   = request.form.get('end_date', '').strip()
        reason    = request.form.get('reason', '').strip()

        if not title or not start_str or not end_str:
            flash('All fields are required.', 'danger')
            return redirect(url_for('admin.manage_holidays'))

        try:
            start_date = datetime.strptime(start_str, '%Y-%m-%d').date()
            end_date   = datetime.strptime(end_str,   '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid date format.', 'danger')
            return redirect(url_for('admin.manage_holidays'))

        if end_date < start_date:
            flash('End date cannot be before start date.', 'danger')
            return redirect(url_for('admin.manage_holidays'))

        holiday = GlobalHoliday(title=title, start_date=start_date, end_date=end_date, reason=reason or None)
        db.session.add(holiday)

        affected = Appointment.query.filter(
            Appointment.date >= start_date,
            Appointment.date <= end_date,
            Appointment.status.in_(['Pending', 'Approved'])
        ).all()

        from utils import send_email
        for apt in affected:
            apt.status         = 'Rejected'
            apt.rejection_note = f'University Holiday: {title}'
            db.session.add(Notification(
                user_id=apt.user_id,
                message=f'Your appointment on {apt.date.strftime("%d %b %Y")} was cancelled due to a university holiday: {title}.'
            ))
            student = db.session.get(User, apt.user_id)
            if student and student.email:
                send_email(
                    "Appointment Cancelled — University Holiday — IUT",
                    [student.email],
                    _holiday_cancellation_email(apt, student, title, start_date, end_date, reason)
                )

        log_action('holiday_added', f"Holiday '{title}' {start_date}–{end_date}. {len(affected)} appointment(s) cancelled.")
        db.session.commit()
        flash(f'Holiday added. {len(affected)} appointment(s) cancelled and students notified by email.', 'success')
        return redirect(url_for('admin.manage_holidays'))

    holidays = GlobalHoliday.query.order_by(GlobalHoliday.start_date).all()
    today    = datetime.now(timezone.utc).date()
    return render_template('admin/holidays.html', holidays=holidays, today=today)


@admin_bp.route('/admin/holidays/delete/<int:holiday_id>')
@login_required
@admin_required
def delete_holiday(holiday_id):
    holiday = db.session.get(GlobalHoliday, holiday_id)
    if not holiday:
        flash('Holiday not found.', 'danger')
        return redirect(url_for('admin.manage_holidays'))
    log_action('holiday_deleted', f"Deleted holiday '{holiday.title}' {holiday.start_date}–{holiday.end_date}")
    db.session.delete(holiday)
    db.session.commit()
    flash('Holiday removed.', 'success')
    return redirect(url_for('admin.manage_holidays'))


def _holiday_cancellation_email(apt, student, title, start_date, end_date, reason):
    duration    = (end_date - start_date).days + 1
    reason_line = f"<p><strong>Reason:</strong> {reason}</p>" if reason else ""
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;padding:24px;border:1px solid #e0e0e0;border-radius:8px;">
      <div style="text-align:center;margin-bottom:24px;">
        <h2 style="color:#d97706;margin:0;">🏖️ University Holiday Notice</h2>
        <p style="color:#6b7280;margin-top:4px;">Islamic University of Technology</p>
      </div>
      <p>Dear <strong>{student.name}</strong>,</p>
      <p>We regret to inform you that your appointment has been <strong>cancelled</strong> due to an upcoming university holiday.</p>
      <div style="background:#fef3c7;border-left:4px solid #d97706;padding:16px;border-radius:4px;margin:20px 0;">
        <h3 style="margin:0 0 8px 0;color:#92400e;">🗓️ Holiday: {title}</h3>
        <p style="margin:4px 0;color:#78350f;">
          <strong>Period:</strong> {start_date.strftime('%d %b %Y')} – {end_date.strftime('%d %b %Y')}
          ({duration} day{'s' if duration > 1 else ''})
        </p>
        {reason_line}
      </div>
      <div style="background:#f9fafb;padding:16px;border-radius:4px;margin:20px 0;">
        <h4 style="margin:0 0 8px 0;color:#374151;">Your Cancelled Appointment</h4>
        <p style="margin:4px 0;"><strong>Officer:</strong> {apt.officer.name}</p>
        <p style="margin:4px 0;"><strong>Date:</strong> {apt.date.strftime('%d %b %Y')}</p>
        <p style="margin:4px 0;"><strong>Time:</strong> {apt.time}</p>
      </div>
      <p>You are welcome to <strong>book a new appointment</strong> once the holiday period ends.</p>
      <div style="text-align:center;margin:28px 0;">
        <a href="https://iut-app.onrender.com/student/book-calcom"
           style="background:#d97706;color:white;padding:12px 28px;border-radius:6px;text-decoration:none;font-weight:bold;">
          Book New Appointment
        </a>
      </div>
      <p style="color:#6b7280;font-size:13px;border-top:1px solid #e5e7eb;padding-top:16px;margin-top:24px;">
        This is an automated message from the IUT Appointment System. Please do not reply to this email.
      </p>
    </div>
    """
