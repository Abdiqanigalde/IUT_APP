from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, Response
from flask_login import login_required, current_user
from models import db, Appointment, User, Officer, Notification, OfficerUnavailability, WaitlistEntry
from forms import AppointmentForm, ProfileForm, RescheduleForm
from datetime import datetime, timedelta, timezone
from flask_bcrypt import Bcrypt
import io, csv

student_bp = Blueprint('student', __name__)
bcrypt = Bcrypt()

# ── Constants ─────────────────────────────────────────────────────────────────

MAX_WAITLIST_PER_STUDENT = 3   # max simultaneous waitlist entries per student
WAITLIST_CUTOFF_MINUTES  = 60  # skip promotion if appointment is within this many minutes


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_unavailability(officer_id, date):
    return OfficerUnavailability.query.filter(
        OfficerUnavailability.officer_id == int(officer_id),
        OfficerUnavailability.start_date <= date,
        OfficerUnavailability.end_date >= date
    ).first()


def officer_slots_for_date(officer, date):
    """Return list of time-slot strings for this officer on this date, respecting working hours."""
    from app import generate_time_slots
    weekday  = date.weekday()
    override = next((wh for wh in officer.working_hours if wh.weekday == weekday), None)
    if override:
        return generate_time_slots(override.start_time, override.end_time)
    return generate_time_slots(officer.work_start or "08:00", officer.work_end or "17:00")


def is_day_off(officer, date):
    return date.weekday() in officer.get_off_days()


def daily_count(officer_id, date):
    return Appointment.query.filter(
        Appointment.officer_id == officer_id,
        Appointment.date == date,
        Appointment.status.in_(['Pending', 'Approved'])
    ).count()


def build_qr_data(apt):
    """Build human-readable QR code string for an appointment."""
    return (
        f"Appointment ID: {apt.id}\n"
        f"Student Name: {apt.student_name}\n"
        f"Student ID: {apt.student_id_num}\n"
        f"Department: {apt.department}\n"
        f"Officer: {apt.officer.name}\n"
        f"Designation: {apt.officer.designation}\n"
        f"Date: {apt.date.strftime('%d %B %Y')}\n"
        f"Time: {apt.time}\n"
        f"Issue: {apt.issue}\n"
        f"Status: {apt.status}\n"
    )


def slot_appointment(officer_id, date, time):
    """Return the active appointment occupying a specific slot, or None."""
    return Appointment.query.filter_by(
        officer_id=officer_id,
        date=date,
        time=time,
    ).filter(Appointment.status.in_(['Pending', 'Approved'])).first()


# ── Dashboard ─────────────────────────────────────────────────────────────────

@student_bp.route('/student/dashboard')
@login_required
def dashboard():
    if current_user.role != 'student':
        return redirect(url_for('index'))

    search_officer = request.args.get('officer', '').strip()
    search_status  = request.args.get('status',  '').strip()
    search_date    = request.args.get('date',    '').strip()

    query = Appointment.query.filter_by(user_id=current_user.id)
    if search_officer:
        query = query.join(Officer).filter(Officer.name.ilike(f'%{search_officer}%'))
    if search_status:
        query = query.filter(Appointment.status == search_status)
    if search_date:
        try:
            d     = datetime.strptime(search_date, '%Y-%m-%d').date()
            query = query.filter(Appointment.date == d)
        except ValueError:
            pass

    appointments  = query.order_by(Appointment.date.desc(), Appointment.time.desc()).all()
    notifications = (
        Notification.query
        .filter_by(user_id=current_user.id, is_read=False)
        .order_by(Notification.created_at.desc())
        .all()
    )

    # Waitlist entries for this student — keyed on slot, with position
    waitlist_entries = (
        WaitlistEntry.query
        .filter_by(user_id=current_user.id)
        .order_by(WaitlistEntry.joined_at)
        .all()
    )
    # Annotate each entry with queue position and slot info
    for entry in waitlist_entries:
        position = (
            WaitlistEntry.query
            .filter_by(
                officer_id=entry.officer_id,
                slot_date=entry.slot_date,
                slot_time=entry.slot_time,
            )
            .filter(WaitlistEntry.joined_at <= entry.joined_at)
            .count()
        )
        entry.queue_position = position

    return render_template(
        'student/dashboard.html',
        appointments=appointments,
        notifications=notifications,
        waitlist_entries=waitlist_entries,
        search_officer=search_officer,
        search_status=search_status,
        search_date=search_date,
    )


@student_bp.route('/student/notifications/read-all')
@login_required
def read_all_notifications():
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    return redirect(url_for('student.dashboard'))


# ── Book appointment ──────────────────────────────────────────────────────────

@student_bp.route('/student/book', methods=['GET', 'POST'])
@login_required
def book_appointment():
    if current_user.role != 'student':
        return redirect(url_for('index'))

    form     = AppointmentForm()
    officers = Officer.query.filter_by(is_active=True).all()
    form.officer.choices = [(o.id, f"{o.name} ({o.designation})") for o in officers]

    from app import generate_time_slots
    form.time.choices = [(s, s) for s in generate_time_slots('06:00', '22:00')]

    if request.method == 'GET':
        if current_user.student_id_num:
            form.student_id_num.data = current_user.student_id_num
        if current_user.department:
            form.department.data = current_user.department

    if form.validate_on_submit():
        booking_date = form.date.data
        day_name     = booking_date.strftime('%A')
        officer      = db.session.get(Officer, form.officer.data)

        # ── Day-off check ─────────────────────────────────────────────────────
        if is_day_off(officer, booking_date):
            flash(f'{officer.name} does not take appointments on {day_name}s.', 'danger')
            return render_template('student/book.html', form=form)

        # ── Unavailability check ──────────────────────────────────────────────
        unavail = get_unavailability(officer.id, booking_date)
        if unavail:
            flash(
                f'<i class="fas fa-ban me-1"></i> <strong>{officer.name}</strong> is unavailable '
                f'({unavail.start_date.strftime("%d %b")} – {unavail.end_date.strftime("%d %b %Y")}). '
                f'Reason: {unavail.reason}',
                'danger'
            )
            return render_template('student/book.html', form=form)

        # ── Daily limit check ─────────────────────────────────────────────────
        if officer.daily_limit > 0 and daily_count(officer.id, booking_date) >= officer.daily_limit:
            flash(f'{officer.name} has reached the maximum appointments for that day.', 'danger')
            return render_template('student/book.html', form=form)

        # ── Student schedule conflict check ───────────────────────────────────
        student_conflict = Appointment.query.filter_by(
            user_id=current_user.id,
            date=booking_date,
            time=form.time.data,
        ).filter(Appointment.status.in_(['Pending', 'Approved'])).first()
        if student_conflict:
            flash('You already have an appointment at this time.', 'danger')
            return render_template('student/book.html', form=form)

        # ── Slot collision check → offer waitlist ─────────────────────────────
        taken = slot_appointment(officer.id, booking_date, form.time.data)
        if taken:
            # Count how many are already waiting for this slot
            waiters = WaitlistEntry.query.filter_by(
                officer_id=officer.id,
                slot_date=booking_date,
                slot_time=form.time.data,
            ).count()
            flash(
                f'This time slot is already booked ({waiters} person(s) waiting). '
                f'You may join the waitlist.',
                'warning'
            )
            return render_template(
                'student/book.html',
                form=form,
                suggest_waitlist=True,
                waitlist_officer_id=officer.id,
                waitlist_date=booking_date.isoformat(),
                waitlist_time=form.time.data,
                waitlist_student_id_num=form.student_id_num.data,
                waitlist_department=form.department.data,
                waitlist_issue=form.issue.data,
                waitlist_student_name=form.student_name.data,
            )

        # ── Create appointment ────────────────────────────────────────────────
        apt = Appointment(
            user_id=current_user.id,
            student_name=form.student_name.data,
            student_id_num=form.student_id_num.data,
            department=form.department.data,
            officer_id=officer.id,
            day=day_name,
            date=booking_date,
            time=form.time.data,
            issue=form.issue.data,
            status='Pending',
        )
        db.session.add(apt)

        current_user.student_id_num = form.student_id_num.data
        current_user.department     = form.department.data

        db.session.flush()          # get apt.id before commit
        apt.qr_code_data = build_qr_data(apt)

        from models import AppointmentTimeline
        db.session.add(AppointmentTimeline(
            appointment_id=apt.id,
            status='Booked',
            note='Appointment created, awaiting admin approval.'
        ))

        db.session.commit()

        from utils import send_email, booking_confirmation_email
        send_email(
            "Appointment Booked — IUT Appointments",
            [current_user.email],
            booking_confirmation_email(apt, current_user)
        )

        flash('Appointment booked successfully! Waiting for approval.', 'success')
        return redirect(url_for('student.dashboard'))

    return render_template('student/book.html', form=form)


# ── Cancel ────────────────────────────────────────────────────────────────────

@student_bp.route('/student/cancel/<int:appointment_id>')
@login_required
def cancel_appointment(appointment_id):
    apt = db.session.get(Appointment, appointment_id)
    if not apt or apt.user_id != current_user.id:
        flash('Not authorized.', 'danger')
        return redirect(url_for('student.dashboard'))
    if apt.status == 'Completed':
        flash('Cannot cancel a completed appointment.', 'danger')
        return redirect(url_for('student.dashboard'))

    apt.status = 'Cancelled'
    db.session.flush()
    _promote_waitlist(apt.officer_id, apt.date, apt.time)
    db.session.commit()
    flash('Appointment cancelled.', 'success')
    return redirect(url_for('student.dashboard'))


# ── Reschedule ────────────────────────────────────────────────────────────────

@student_bp.route('/student/reschedule/<int:appointment_id>', methods=['GET', 'POST'])
@login_required
def reschedule_appointment(appointment_id):
    apt = db.session.get(Appointment, appointment_id)
    if not apt or apt.user_id != current_user.id:
        flash('Not authorized.', 'danger')
        return redirect(url_for('student.dashboard'))
    if apt.status == 'Completed':
        flash('Cannot reschedule a completed appointment.', 'danger')
        return redirect(url_for('student.dashboard'))

    officer = apt.officer
    form    = RescheduleForm()

    from app import generate_time_slots
    form.time.choices = [(s, s) for s in generate_time_slots('06:00', '22:00')]

    if request.method == 'POST':
        new_date_str = request.form.get('date', '').strip()
        new_time     = request.form.get('time', '').strip()

        try:
            new_date = datetime.strptime(new_date_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid date selected.', 'danger')
            return render_template('student/reschedule.html', form=form, apt=apt)

        if not new_time:
            flash('Please select a time slot.', 'danger')
            return render_template('student/reschedule.html', form=form, apt=apt)

        day_name = new_date.strftime('%A')

        if is_day_off(officer, new_date):
            flash(f'{officer.name} does not take appointments on {day_name}s.', 'danger')
            return render_template('student/reschedule.html', form=form, apt=apt)

        unavail = get_unavailability(officer.id, new_date)
        if unavail:
            flash(f'{officer.name} is unavailable that period: {unavail.reason}', 'danger')
            return render_template('student/reschedule.html', form=form, apt=apt)

        conflict = Appointment.query.filter_by(
            officer_id=officer.id, date=new_date, time=new_time
        ).filter(
            Appointment.id != apt.id,
            Appointment.status.in_(['Pending', 'Approved'])
        ).first()
        if conflict:
            flash('That slot is already taken. Please pick another.', 'danger')
            return render_template('student/reschedule.html', form=form, apt=apt)

        self_conflict = Appointment.query.filter_by(
            user_id=current_user.id, date=new_date, time=new_time
        ).filter(
            Appointment.id != apt.id,
            Appointment.status.in_(['Pending', 'Approved'])
        ).first()
        if self_conflict:
            flash('You already have another appointment at that time.', 'danger')
            return render_template('student/reschedule.html', form=form, apt=apt)

        old_officer_id = apt.officer_id
        old_date       = apt.date
        old_time       = apt.time

        apt.date   = new_date
        apt.time   = new_time
        apt.day    = day_name
        apt.status = 'Pending'
        db.session.flush()

        _promote_waitlist(old_officer_id, old_date, old_time)

        db.session.commit()
        flash('Appointment rescheduled successfully!', 'success')
        return redirect(url_for('student.dashboard'))

    if request.method == 'GET':
        form.date.data = apt.date

    return render_template('student/reschedule.html', form=form, apt=apt)


# ── Waitlist ──────────────────────────────────────────────────────────────────

@student_bp.route('/student/waitlist/join', methods=['POST'])
@login_required
def join_waitlist():
    """
    Join the waitlist for a specific (officer, date, time) slot.
    All three identifiers come from the form, NOT from an appointment_id,
    so the waitlist survives appointment cancellations and reschedules.
    """
    officer_id     = request.form.get('officer_id', type=int)
    slot_date_str  = request.form.get('slot_date', '')
    slot_time      = request.form.get('slot_time', '').strip()
    student_name   = request.form.get('student_name',   current_user.name).strip()
    student_id_num = request.form.get('student_id_num', current_user.student_id_num or '').strip()
    department     = request.form.get('department',     current_user.department or '').strip()
    issue          = request.form.get('issue', '').strip()

    # Validate inputs
    if not officer_id or not slot_date_str or not slot_time:
        flash('Missing slot information. Please try booking again.', 'danger')
        return redirect(url_for('student.book_appointment'))

    try:
        slot_date = datetime.strptime(slot_date_str, '%Y-%m-%d').date()
    except ValueError:
        flash('Invalid date format.', 'danger')
        return redirect(url_for('student.book_appointment'))

    officer = db.session.get(Officer, officer_id)
    if not officer:
        flash('Officer not found.', 'danger')
        return redirect(url_for('student.book_appointment'))

    # Slot must still be taken (no point joining if it's now open)
    taken = slot_appointment(officer_id, slot_date, slot_time)
    if not taken:
        flash('That slot is now available — go ahead and book it directly!', 'info')
        return redirect(url_for('student.book_appointment'))

    # Enforce per-student waitlist cap
    active_count = WaitlistEntry.query.filter_by(user_id=current_user.id).count()
    if active_count >= MAX_WAITLIST_PER_STUDENT:
        flash(
            f'You can only be on {MAX_WAITLIST_PER_STUDENT} waitlists at a time. '
            f'Please leave one before joining another.',
            'warning'
        )
        return redirect(url_for('student.dashboard'))

    # Duplicate check for this exact slot
    already = WaitlistEntry.query.filter_by(
        officer_id=officer_id,
        slot_date=slot_date,
        slot_time=slot_time,
        user_id=current_user.id,
    ).first()
    if already:
        flash('You are already on the waitlist for this slot.', 'info')
        return redirect(url_for('student.dashboard'))

    # Calculate queue position before inserting
    current_waiters = WaitlistEntry.query.filter_by(
        officer_id=officer_id,
        slot_date=slot_date,
        slot_time=slot_time,
    ).count()

    entry = WaitlistEntry(
        officer_id=officer_id,
        slot_date=slot_date,
        slot_time=slot_time,
        user_id=current_user.id,
        student_name=student_name,
        student_id_num=student_id_num,
        department=department,
        issue=issue,
    )
    db.session.add(entry)
    db.session.commit()

    flash(
        f'You are #{current_waiters + 1} on the waitlist for '
        f'{officer.name} on {slot_date.strftime("%d %b %Y")} at {slot_time}. '
        f'We will notify you if the slot opens.',
        'info'
    )
    return redirect(url_for('student.dashboard'))


@student_bp.route('/student/waitlist/leave/<int:entry_id>')
@login_required
def leave_waitlist(entry_id):
    entry = db.session.get(WaitlistEntry, entry_id)
    if not entry or entry.user_id != current_user.id:
        flash('Not authorized.', 'danger')
        return redirect(url_for('student.dashboard'))
    db.session.delete(entry)
    db.session.commit()
    flash('Removed from waitlist.', 'info')
    return redirect(url_for('student.dashboard'))


@student_bp.route('/student/waitlist')
@login_required
def my_waitlist():
    """Dedicated page showing the student's waitlist entries with positions."""
    entries = (
        WaitlistEntry.query
        .filter_by(user_id=current_user.id)
        .order_by(WaitlistEntry.joined_at)
        .all()
    )
    now = datetime.now(timezone.utc)
    for entry in entries:
        # Queue position
        entry.queue_position = (
            WaitlistEntry.query
            .filter_by(
                officer_id=entry.officer_id,
                slot_date=entry.slot_date,
                slot_time=entry.slot_time,
            )
            .filter(WaitlistEntry.joined_at <= entry.joined_at)
            .count()
        )
        # Total waiters for this slot
        entry.total_waiters = WaitlistEntry.query.filter_by(
            officer_id=entry.officer_id,
            slot_date=entry.slot_date,
            slot_time=entry.slot_time,
        ).count()
        # Warn if the appointment is very soon
        slot_dt = datetime.combine(entry.slot_date, datetime.strptime(
            entry.slot_time.split(' - ')[0].strip(), '%I:%M %p'
        ).time()).replace(tzinfo=timezone.utc)
        entry.is_imminent = (slot_dt - now) < timedelta(hours=2)

    return render_template('student/waitlist.html', entries=entries)


def _promote_waitlist(officer_id, slot_date, slot_time):
    """
    When a slot (officer_id, slot_date, slot_time) opens up, promote the
    first eligible waitlist entry to a new Appointment.

    Key fixes vs original:
      - Keyed on (officer_id, slot_date, slot_time), NOT appointment_id
      - Skips promotion if appointment is within WAITLIST_CUTOFF_MINUTES
      - Checks promoted student has no schedule conflict at that slot
      - Commits only after all DB objects are ready; email sent after commit
    """
    now = datetime.now(timezone.utc)

    # Skip if the slot is too soon to be useful
    try:
        slot_dt = datetime.combine(
            slot_date,
            datetime.strptime(slot_time.split(' - ')[0].strip(), '%I:%M %p').time()
        ).replace(tzinfo=timezone.utc)
        if (slot_dt - now).total_seconds() < WAITLIST_CUTOFF_MINUTES * 60:
            return
    except ValueError:
        pass  # Can't parse time — proceed anyway

    officer = db.session.get(Officer, officer_id)
    if not officer:
        return

    candidates = (
        WaitlistEntry.query
        .filter_by(officer_id=officer_id, slot_date=slot_date, slot_time=slot_time)
        .order_by(WaitlistEntry.joined_at)
        .all()
    )

    for first in candidates:
        user = db.session.get(User, first.user_id)
        if not user:
            db.session.delete(first)
            continue

        # Check promoted student has no conflict at this slot
        conflict = Appointment.query.filter_by(
            user_id=first.user_id,
            date=slot_date,
            time=slot_time,
        ).filter(Appointment.status.in_(['Pending', 'Approved'])).first()
        if conflict:
            # Skip this person — they already have something at this time
            db.session.delete(first)
            continue

        day_name = slot_date.strftime('%A')
        new_apt  = Appointment(
            user_id=first.user_id,
            student_name=first.student_name,
            student_id_num=first.student_id_num,
            department=first.department,
            officer_id=officer_id,
            day=day_name,
            date=slot_date,
            time=slot_time,
            issue=first.issue,
            status='Pending',
        )
        db.session.add(new_apt)
        db.session.delete(first)
        db.session.flush()          # get new_apt.id

        new_apt.qr_code_data = build_qr_data(new_apt)

        notif = Notification(
            user_id=first.user_id,
            message=(
                f"Great news! A slot opened up with {officer.name} "
                f"on {slot_date.strftime('%d %b %Y')} at {slot_time}. "
                f"You have been automatically booked!"
            )
        )
        db.session.add(notif)

        # Commit everything BEFORE sending email so a mail failure
        # doesn't roll back the appointment.
        db.session.commit()

        try:
            from utils import send_email, waitlist_promoted_email
            send_email(
                "Waitlist Slot Available — IUT Appointments",
                [user.email],
                waitlist_promoted_email(new_apt, user)
            )
        except Exception as mail_err:
            # Log but don't crash — appointment is already saved
            print(f'[IUT] Waitlist promotion email failed for user {user.id}: {mail_err}')

        return  # Only promote one person per slot opening


# ── Slots API ─────────────────────────────────────────────────────────────────

@student_bp.route('/api/slots')
@login_required
def get_slots():
    officer_id = request.args.get('officer')
    date_str   = request.args.get('date')
    if not officer_id or not date_str:
        return jsonify({'unavailable': False, 'slots': []})

    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'unavailable': False, 'slots': []})

    officer = db.session.get(Officer, int(officer_id))
    if not officer:
        return jsonify({'unavailable': False, 'slots': []})

    if is_day_off(officer, date_obj):
        return jsonify({
            'unavailable': True,
            'reason': 'Recurring day off',
            'officer_name': officer.name,
            'start_date': date_str,
            'end_date': date_str,
            'slots': []
        })

    unavail = get_unavailability(officer_id, date_obj)
    if unavail:
        return jsonify({
            'unavailable': True,
            'reason': unavail.reason,
            'officer_name': officer.name,
            'start_date': unavail.start_date.strftime('%d %b %Y'),
            'end_date':   unavail.end_date.strftime('%d %b %Y'),
            'slots': []
        })

    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'services'))
    from appointment_service import AppointmentService

    available_slots = AppointmentService.get_available_slots(officer.id, date_obj)
    all_slots       = officer_slots_for_date(officer, date_obj)
    limit_reached   = officer.daily_limit > 0 and daily_count(officer.id, date_obj) >= officer.daily_limit

    slot_data = []
    for s in all_slots:
        waiters = WaitlistEntry.query.filter_by(
            officer_id=officer.id,
            slot_date=date_obj,
            slot_time=s,
        ).count()
        slot_data.append({
            'time':      s,
            'available': s in available_slots,
            'waiters':   waiters,
        })

    return jsonify({
        'unavailable':   False,
        'limit_reached': limit_reached,
        'slots':         slot_data,
    })


# ── Calendar API ──────────────────────────────────────────────────────────────

@student_bp.route('/api/calendar')
@login_required
def calendar_data():
    """Return availability status for each day in a month for an officer."""
    officer_id = request.args.get('officer')
    year       = int(request.args.get('year',  datetime.now(timezone.utc).year))
    month      = int(request.args.get('month', datetime.now(timezone.utc).month))
    if not officer_id:
        return jsonify([])

    officer = db.session.get(Officer, int(officer_id))
    if not officer:
        return jsonify([])

    import calendar
    days_in_month = calendar.monthrange(year, month)[1]
    result = []

    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'services'))
    from appointment_service import AppointmentService

    for day in range(1, days_in_month + 1):
        d = datetime(year, month, day).date()
        if d < datetime.now(timezone.utc).date():
            result.append({'date': d.isoformat(), 'status': 'past'})
            continue
        if is_day_off(officer, d):
            result.append({'date': d.isoformat(), 'status': 'off'})
            continue
        if get_unavailability(int(officer_id), d):
            result.append({'date': d.isoformat(), 'status': 'unavailable'})
            continue
        if officer.daily_limit > 0 and daily_count(officer.id, d) >= officer.daily_limit:
            result.append({'date': d.isoformat(), 'status': 'full'})
            continue
        available = AppointmentService.get_available_slots(officer.id, d)
        result.append({'date': d.isoformat(), 'status': 'available' if available else 'full'})

    return jsonify(result)


# ── Export PDF ────────────────────────────────────────────────────────────────

@student_bp.route('/student/export/pdf')
@login_required
def export_pdf():
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    import io as _io

    appointments = (
        Appointment.query
        .filter_by(user_id=current_user.id)
        .order_by(Appointment.date.desc())
        .all()
    )

    buf = _io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            rightMargin=30, leftMargin=30,
                            topMargin=30, bottomMargin=18)
    styles   = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph("IUT Appointment History", styles['Title']))
    elements.append(Paragraph(
        f"Student: {current_user.name} | "
        f"Generated: {datetime.now(timezone.utc).strftime('%d %b %Y %H:%M')}",
        styles['Normal']
    ))
    elements.append(Spacer(1, 12))

    data = [['#', 'Officer', 'Date', 'Time', 'Reason', 'Status']]
    for i, apt in enumerate(appointments, 1):
        data.append([
            str(i),
            apt.officer.name,
            apt.date.strftime('%d %b %Y'),
            apt.time,
            apt.issue[:40] + ('…' if len(apt.issue) > 40 else ''),
            apt.status,
        ])

    t = Table(data, colWidths=[25, 100, 85, 130, 130, 70])
    t.setStyle(TableStyle([
        ('BACKGROUND',     (0, 0), (-1, 0),  colors.HexColor('#4361ee')),
        ('TEXTCOLOR',      (0, 0), (-1, 0),  colors.white),
        ('FONTNAME',       (0, 0), (-1, 0),  'Helvetica-Bold'),
        ('FONTSIZE',       (0, 0), (-1, -1), 8),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
        ('GRID',           (0, 0), (-1, -1), 0.5, colors.HexColor('#dee2e6')),
        ('PADDING',        (0, 0), (-1, -1), 6),
    ]))
    elements.append(t)
    doc.build(elements)
    buf.seek(0)
    return Response(buf, mimetype='application/pdf',
                    headers={'Content-Disposition': 'attachment; filename=my_appointments.pdf'})


# ── Print slip ────────────────────────────────────────────────────────────────

@student_bp.route('/student/print/<int:appointment_id>')
@login_required
def print_slip(appointment_id):
    apt = db.session.get(Appointment, appointment_id)
    if not apt or apt.user_id != current_user.id:
        flash('Not authorized.', 'danger')
        return redirect(url_for('student.dashboard'))
    return render_template('student/print_slip.html', apt=apt)


# ── Profile ───────────────────────────────────────────────────────────────────

@student_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    form = ProfileForm()
    if form.validate_on_submit():
        if form.email.data != current_user.email:
            if User.query.filter_by(email=form.email.data).first():
                flash('That email is already in use.', 'danger')
                return render_template('profile.html', form=form)
        current_user.name           = form.name.data
        current_user.email          = form.email.data
        current_user.student_id_num = form.student_id_num.data
        current_user.department     = form.department.data
        if form.new_password.data:
            if not form.current_password.data or \
               not bcrypt.check_password_hash(current_user.password, form.current_password.data):
                flash('Current password is incorrect.', 'danger')
                return render_template('profile.html', form=form)
            current_user.password = bcrypt.generate_password_hash(
                form.new_password.data
            ).decode('utf-8')
        db.session.commit()
        flash('Profile updated!', 'success')
        return redirect(url_for('student.profile'))
    elif request.method == 'GET':
        form.name.data           = current_user.name
        form.email.data          = current_user.email
        form.student_id_num.data = current_user.student_id_num
        form.department.data     = current_user.department
    return render_template('profile.html', form=form)


# ── Dark mode toggle ──────────────────────────────────────────────────────────

@student_bp.route('/toggle-darkmode', methods=['POST'])
@login_required
def toggle_darkmode():
    current_user.dark_mode = not current_user.dark_mode
    db.session.commit()
    return jsonify({'dark_mode': current_user.dark_mode})


# ── Officer list & profile ────────────────────────────────────────────────────

@student_bp.route('/officers')
@login_required
def officer_list():
    officers = Officer.query.filter_by(is_active=True).all()
    today    = datetime.now(timezone.utc).date()
    return render_template('student/officers.html', officers=officers, today=today)


@student_bp.route('/officer/<int:officer_id>')
@login_required
def officer_profile(officer_id):
    officer = db.session.get(Officer, officer_id)
    if not officer:
        from flask import abort
        abort(404)
    today      = datetime.now(timezone.utc).date()
    unavail    = get_unavailability(officer_id, today)
    total_apts = Appointment.query.filter_by(officer_id=officer_id).count()
    return render_template('student/officer_profile.html', officer=officer,
                           today=today, unavail=unavail, total_apts=total_apts)


# ── QR Code PNG endpoint ──────────────────────────────────────────────────────

@student_bp.route('/student/qr/<int:appointment_id>.png')
@login_required
def qr_image(appointment_id):
    apt = db.session.get(Appointment, appointment_id)
    if not apt or apt.user_id != current_user.id:
        from flask import abort; abort(403)
    if not apt.qr_code_data:
        from flask import abort; abort(404)
    import io
    try:
        import qrcode
        qr = qrcode.QRCode(version=1, box_size=8, border=2)
        qr.add_data(apt.qr_code_data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format='PNG')
    except ImportError:
        from PIL import Image, ImageDraw
        img  = Image.new('RGB', (200, 200), color='white')
        draw = ImageDraw.Draw(img)
        draw.rectangle([10, 10, 190, 190], outline='black', width=3)
        buf  = io.BytesIO()
        img.save(buf, format='PNG')
    buf.seek(0)
    return Response(buf, mimetype='image/png',
                    headers={'Cache-Control': 'max-age=3600'})


# ── Live appointment status API ───────────────────────────────────────────────

@student_bp.route('/api/my-appointments/status')
@login_required
def my_appointments_status():
    apts = (
        Appointment.query
        .filter_by(user_id=current_user.id)
        .order_by(Appointment.date.desc())
        .all()
    )
    return jsonify([{
        'id':      a.id,
        'status':  a.status,
        'officer': a.officer.name,
        'date':    str(a.date),
        'time':    a.time,
        'qr_data': a.qr_code_data or '',
    } for a in apts])


# ── AI Suggestions API ────────────────────────────────────────────────────────

@student_bp.route('/api/ai-suggest')
@login_required
def ai_suggest():
    issue    = request.args.get('issue', '').strip()
    date_str = request.args.get('date', '')

    if not issue:
        return jsonify({'error': 'Please describe your issue first.'}), 400

    try:
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'services'))
        from ai_suggestions import AISuggestionsService
        from appointment_service import AppointmentService
    except ImportError as e:
        return jsonify({'error': f'AI service unavailable: {e}'}), 500

    try:
        from datetime import datetime as dt
        preferred_date = dt.strptime(date_str, '%Y-%m-%d').date() if date_str else dt.now().date()
    except ValueError:
        from datetime import datetime as dt
        preferred_date = dt.now().date()

    recommendations = AISuggestionsService.recommend_officers(issue, num_recommendations=3)

    result = []
    for rec in recommendations:
        officer = rec['officer']
        if not officer.is_active:
            continue
        slots = AppointmentService.get_available_slots(officer.id, preferred_date)
        result.append({
            'officer_id':  officer.id,
            'name':        officer.name,
            'designation': officer.designation,
            'score':       round(rec['score'], 1),
            'reason':      rec['reason'],
            'handles':     officer.handles or '',
            'slots_today': slots[:5],
        })

    return jsonify({
        'issue':           issue,
        'date':            str(preferred_date),
        'recommendations': result,
    })


# ══════════════════════════════════════════════════════════════════════════════
#  Cal.com-style booking routes — added for modern UI
# ══════════════════════════════════════════════════════════════════════════════

@student_bp.route('/student/book-calcom', methods=['GET'])
@login_required
def book_calcom():
    """Cal.com-style booking page — multi-step: choose officer → date/time → confirm."""
    if current_user.role != 'student':
        return redirect(url_for('index'))
    from forms import AppointmentForm
    form = AppointmentForm()
    officers = Officer.query.filter_by(is_active=True).all()
    return render_template('student/book_calcom.html', form=form, officers=officers)


@student_bp.route('/student/book-calcom/submit', methods=['POST'])
@login_required
def book_calcom_submit():
    """Process the Cal.com booking form submission."""
    if current_user.role != 'student':
        return redirect(url_for('index'))

    officer_id   = request.form.get('officer_id', type=int)
    date_str     = request.form.get('date', '').strip()
    time_str     = request.form.get('time', '').strip()
    duration     = request.form.get('duration', 15, type=int)
    meeting_type = request.form.get('meeting_type', 'in_person').strip()
    issue        = request.form.get('issue', '').strip()
    student_name = request.form.get('student_name', current_user.name).strip()
    student_id   = request.form.get('student_id_num', current_user.student_id_num or '').strip()
    department   = request.form.get('department', current_user.department or '').strip()

    # ── Validate inputs ───────────────────────────────────────────────────────
    if not all([officer_id, date_str, time_str, issue, student_id, department]):
        flash('Please fill in all required fields.', 'danger')
        return redirect(url_for('student.book_calcom'))

    try:
        booking_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        flash('Invalid date.', 'danger')
        return redirect(url_for('student.book_calcom'))

    officer = db.session.get(Officer, officer_id)
    if not officer:
        flash('Officer not found.', 'danger')
        return redirect(url_for('student.book_calcom'))

    day_name = booking_date.strftime('%A')

    # ── Day-off / unavailability / limit checks ───────────────────────────────
    if is_day_off(officer, booking_date):
        flash(f'{officer.name} does not take appointments on {day_name}s.', 'danger')
        return redirect(url_for('student.book_calcom'))

    unavail = get_unavailability(officer.id, booking_date)
    if unavail:
        flash(f'{officer.name} is unavailable: {unavail.reason}', 'danger')
        return redirect(url_for('student.book_calcom'))

    if officer.daily_limit > 0 and daily_count(officer.id, booking_date) >= officer.daily_limit:
        flash(f'{officer.name} has reached the max appointments for that day.', 'danger')
        return redirect(url_for('student.book_calcom'))

    # ── Student self-conflict ─────────────────────────────────────────────────
    student_conflict = Appointment.query.filter_by(
        user_id=current_user.id, date=booking_date, time=time_str,
    ).filter(Appointment.status.in_(['Pending', 'Approved'])).first()
    if student_conflict:
        flash('You already have an appointment at this time.', 'danger')
        return redirect(url_for('student.book_calcom'))

    # ── Slot collision check ──────────────────────────────────────────────────
    taken = slot_appointment(officer.id, booking_date, time_str)
    if taken:
        waiters = WaitlistEntry.query.filter_by(
            officer_id=officer.id, slot_date=booking_date, slot_time=time_str,
        ).count()
        flash(f'That slot was just taken ({waiters} waiting). Please choose another.', 'warning')
        return redirect(url_for('student.book_calcom'))

    # ── Create appointment ────────────────────────────────────────────────────
    apt = Appointment(
        user_id        = current_user.id,
        student_name   = student_name,
        student_id_num = student_id,
        department     = department,
        officer_id     = officer.id,
        day            = day_name,
        date           = booking_date,
        time           = time_str,
        issue          = issue,
        status         = 'Pending',
        duration       = max(5, min(duration, 480)),
        meeting_type   = meeting_type,
        location       = officer.room or '',
        timezone       = 'Asia/Dhaka',
        notes          = issue,
    )
    db.session.add(apt)
    current_user.student_id_num = student_id
    current_user.department     = department
    db.session.flush()
    apt.qr_code_data = build_qr_data(apt)

    from models import AppointmentTimeline, AppointmentHistory
    db.session.add(AppointmentTimeline(
        appointment_id = apt.id,
        status         = 'Booked',
        note           = f'Booked via Cal.com UI. Duration: {duration}min, Type: {meeting_type}.'
    ))
    db.session.add(AppointmentHistory(
        appointment_id = apt.id,
        action         = 'created',
        new_value      = f'{booking_date} {time_str} with {officer.name}',
        changed_by     = current_user.id,
        note           = 'Appointment created via modern booking flow.'
    ))

    db.session.commit()

    from utils import send_email, booking_confirmation_email
    send_email(
        "Appointment Booked — IUT Appointments",
        [current_user.email],
        booking_confirmation_email(apt, current_user)
    )

    flash('Appointment booked successfully! Pending approval.', 'success')
    return redirect(url_for('student.dashboard'))


@student_bp.route('/api/slots/calcom')
@login_required
def get_slots_calcom():
    """
    Duration-aware slot API for Cal.com booking UI.
    Generates slots based on selected duration and removes any overlapping booked slots.
    """
    officer_id  = request.args.get('officer', type=int)
    date_str    = request.args.get('date', '')
    duration    = request.args.get('duration', 15, type=int)
    duration    = max(5, min(duration, 480))

    if not officer_id or not date_str:
        return jsonify({'unavailable': False, 'slots': []})

    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'unavailable': False, 'slots': []})

    officer = db.session.get(Officer, officer_id)
    if not officer:
        return jsonify({'unavailable': False, 'slots': []})

    # Off / unavailable checks
    if is_day_off(officer, date_obj):
        return jsonify({'unavailable': True, 'reason': 'Day off', 'slots': []})

    unavail = get_unavailability(officer_id, date_obj)
    if unavail:
        return jsonify({'unavailable': True, 'reason': unavail.reason, 'slots': []})

    # Determine work window for the day
    weekday  = date_obj.weekday()
    override = next((wh for wh in officer.working_hours if wh.weekday == weekday), None)
    if override:
        work_start_str, work_end_str = override.start_time, override.end_time
    else:
        work_start_str = officer.work_start or '08:00'
        work_end_str   = officer.work_end   or '17:00'

    # Parse work window
    def parse_hm(s):
        h, m = map(int, s.split(':'))
        return h * 60 + m

    ws = parse_hm(work_start_str)
    we = parse_hm(work_end_str)

    # Get all booked slots for the day and their durations
    booked_apts = Appointment.query.filter(
        Appointment.officer_id == officer_id,
        Appointment.date == date_obj,
        Appointment.status.in_(['Pending', 'Approved'])
    ).all()

    # Convert booked appointments to (start_min, end_min) blocks
    def parse_time_str(t):
        """Parse '8:00 AM', '08:00', '08:00 AM' → minutes from midnight."""
        t = t.strip()
        if 'AM' in t.upper() or 'PM' in t.upper():
            from datetime import datetime as _dt
            try:
                return _dt.strptime(t, '%I:%M %p').hour * 60 + _dt.strptime(t, '%I:%M %p').minute
            except:
                try:
                    return _dt.strptime(t, '%I:%M%p').hour * 60 + _dt.strptime(t, '%I:%M%p').minute
                except:
                    pass
        try:
            h, m = map(int, t.split(':'))
            return h * 60 + m
        except:
            return -1

    booked_blocks = []
    for apt in booked_apts:
        start = parse_time_str(apt.time)
        dur   = apt.duration if apt.duration else 15
        if start >= 0:
            booked_blocks.append((start, start + dur))

    # Generate duration-aligned slots
    slots = []
    cur = ws
    now_min = -1
    today = datetime.now().date()
    now_total = datetime.now().hour * 60 + datetime.now().minute if date_obj == today else -1

    while cur + duration <= we:
        slot_end = cur + duration
        h, m = divmod(cur, 60)
        time_str = f"{h:02d}:{m:02d}"

        # Check if this slot overlaps any booked block
        overlap = any(
            not (slot_end <= b[0] or cur >= b[1])
            for b in booked_blocks
        )

        # Check waiters for THIS exact slot time
        waiters = WaitlistEntry.query.filter_by(
            officer_id=officer_id,
            slot_date=date_obj,
            slot_time=time_str,
        ).count()

        # Past time check
        is_past = (date_obj == today and cur <= now_total)

        slots.append({
            'time':      time_str,
            'available': not overlap and not is_past,
            'waiters':   waiters,
        })

        cur += duration

    return jsonify({'unavailable': False, 'slots': slots})


# ── Visa Guide ────────────────────────────────────────────────────────────────

@student_bp.route('/student/visa-guide')
@login_required
def visa_guide():
    if current_user.role != 'student':
        return redirect(url_for('index'))
    return render_template('student/visa_guide.html')
