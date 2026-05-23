from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    flash,
    request,
    Response,
    jsonify
)

from flask_login import login_required, current_user

from models import (
    db,
    Appointment,
    User,
    Officer,
    Notification,
    OfficerUnavailability,
    AuditLog,
    OfficerWorkingHours,
    AppointmentTimeline
)

from forms import (
    OfficerForm,
    UnavailabilityForm,
    WorkingHoursForm,
    RejectNoteForm,
    OfficerProfileForm,
    ProfileForm
)

from datetime import datetime, timedelta, timezone

import csv
import io
import secrets

from flask_bcrypt import Bcrypt

# ─────────────────────────────────────────────────────────────
# INIT
# ─────────────────────────────────────────────────────────────
admin_bp = Blueprint('admin', __name__)

bcrypt = Bcrypt()


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────
def admin_required(f):
    from functools import wraps

    @wraps(f)
    def decorated(*args, **kwargs):
        if current_user.role not in ('admin', 'super_admin'):
            return redirect(url_for('index'))
        return f(*args, **kwargs)

    return decorated


def log_action(action, detail):
    db.session.add(
        AuditLog(
            admin_id=current_user.id,
            action=action,
            detail=detail
        )
    )


# ─────────────────────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────────────────────
@admin_bp.route('/admin/dashboard')
@login_required
@admin_required
def dashboard():

    today = datetime.now(timezone.utc).date()

    # Appointment stats
    total = Appointment.query.count()
    pending = Appointment.query.filter_by(status='Pending').count()
    approved = Appointment.query.filter_by(status='Approved').count()
    completed = Appointment.query.filter_by(status='Completed').count()
    rejected = Appointment.query.filter_by(status='Rejected').count()
    cancelled = Appointment.query.filter_by(status='Cancelled').count()

    # Student stats
    total_students = User.query.filter_by(role='student').count()
    active_students = User.query.filter_by(
        role='student',
        is_active=True
    ).count()

    # Today's schedule
    today_schedule = Appointment.query.filter_by(
        date=today
    ).order_by(Appointment.time).all()

    # Weekly chart
    weekly = []

    for i in range(6, -1, -1):
        d = today - timedelta(days=i)

        count = Appointment.query.filter(
            Appointment.date == d
        ).count()

        weekly.append({
            'date': d.strftime('%a %d'),
            'count': count
        })

    # Monthly chart
    months_data = []

    for m in range(1, 13):

        count = Appointment.query.filter(
            db.extract('month', Appointment.date) == m,
            db.extract('year', Appointment.date) == today.year
        ).count()

        months_data.append({
            'label': datetime(today.year, m, 1).strftime('%b'),
            'count': count
        })

    # Officer stats
    all_officers = Officer.query.all()

    officer_names = [o.name for o in all_officers]

    officer_counts = [
        Appointment.query.filter_by(officer_id=o.id).count()
        for o in all_officers
    ]

    officer_stats = []

    for officer in all_officers:

        total_count = Appointment.query.filter_by(
            officer_id=officer.id
        ).count()

        approved_count = Appointment.query.filter_by(
            officer_id=officer.id,
            status='Approved'
        ).count()

        completed_count = Appointment.query.filter_by(
            officer_id=officer.id,
            status='Completed'
        ).count()

        rejected_count = Appointment.query.filter_by(
            officer_id=officer.id,
            status='Rejected'
        ).count()

        officer_stats.append({
            'name': officer.name,
            'total': total_count,
            'approved': approved_count,
            'completed': completed_count,
            'rejected': rejected_count
        })

    status_counts = {
        'Pending': pending,
        'Approved': approved,
        'Completed': completed,
        'Rejected': rejected,
        'Cancelled': cancelled
    }

    return render_template(
        'admin/dashboard.html',
        total=total,
        pending=pending,
        approved=approved,
        completed=completed,
        rejected=rejected,
        cancelled=cancelled,
        total_students=total_students,
        active_students=active_students,
        today_schedule=today_schedule,
        officers=officer_names,
        officer_counts=officer_counts,
        officer_stats=officer_stats,
        status_counts=status_counts,
        weekly=weekly,
        months_data=months_data,
        year=today.year
    )


# ─────────────────────────────────────────────────────────────
# APPOINTMENTS
# ─────────────────────────────────────────────────────────────
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
            selected_date = datetime.strptime(
                date_filter,
                '%Y-%m-%d'
            ).date()

            query = query.filter(
                Appointment.date == selected_date
            )

        except ValueError:
            pass

    appointments = query.order_by(
        Appointment.date.desc(),
        Appointment.time.desc()
    ).all()

    all_officers = Officer.query.all()

    # BULK ACTIONS
    if request.method == 'POST':

        selected_ids = request.form.getlist('selected_ids')
        bulk_action = request.form.get('bulk_action')

        if selected_ids and bulk_action in ['Approved', 'Rejected']:

            from utils import (
                send_email,
                appointment_status_email
            )

            for appointment_id in selected_ids:

                appointment = db.session.get(
                    Appointment,
                    int(appointment_id)
                )

                if appointment and appointment.status == 'Pending':

                    appointment.status = bulk_action

                    message = (
                        f"Your appointment with "
                        f"{appointment.officer.name} on "
                        f"{appointment.date.strftime('%d %b %Y')} "
                        f"has been {bulk_action}."
                    )

                    db.session.add(
                        Notification(
                            user_id=appointment.user_id,
                            message=message
                        )
                    )

                    student = db.session.get(
                        User,
                        appointment.user_id
                    )

                    send_email(
                        f"Appointment {bulk_action} — IUT",
                        [student.email],
                        appointment_status_email(
                            appointment,
                            bulk_action
                        )
                    )

            log_action(
                f'bulk_{bulk_action.lower()}',
                f'Bulk {bulk_action} on '
                f'{len(selected_ids)} appointment(s)'
            )

            db.session.commit()

            flash(
                f'{len(selected_ids)} appointment(s) '
                f'{bulk_action.lower()}.',
                'success'
            )

        return redirect(
            url_for(
                'admin.manage_appointments',
                officer=officer_filter,
                status=status_filter,
                date=date_filter
            )
        )

    return render_template(
        'admin/appointments.html',
        appointments=appointments,
        all_officers=all_officers,
        officer_filter=officer_filter,
        status_filter=status_filter,
        date_filter=date_filter
    )


# ─────────────────────────────────────────────────────────────
# UPDATE STATUS
# ─────────────────────────────────────────────────────────────
@admin_bp.route(
    '/admin/update_status/<int:appointment_id>/<string:status>',
    methods=['GET', 'POST']
)
@login_required
@admin_required
def update_status(appointment_id, status):

    appointment = db.session.get(
        Appointment,
        appointment_id
    )

    if not appointment:
        return redirect(url_for('admin.manage_appointments'))

    # REJECTED
    if status == 'Rejected':

        form = RejectNoteForm()

        if form.validate_on_submit():

            appointment.status = 'Rejected'
            appointment.rejection_note = form.rejection_note.data

            message = (
                f"Your appointment with "
                f"{appointment.officer.name} on "
                f"{appointment.date.strftime('%d %b %Y')} "
                f"was rejected. Reason: "
                f"{form.rejection_note.data}"
            )

            db.session.add(
                Notification(
                    user_id=appointment.user_id,
                    message=message
                )
            )

            from utils import (
                send_email,
                rejection_email
            )

            student = db.session.get(
                User,
                appointment.user_id
            )

            send_email(
                "Appointment Rejected — IUT",
                [student.email],
                rejection_email(
                    appointment,
                    student,
                    form.rejection_note.data
                )
            )

            from routes.student import _promote_waitlist

            _promote_waitlist(appointment)

            log_action(
                'appointment_rejected',
                f'#{appointment.id} rejected'
            )

            db.session.commit()

            flash(
                'Appointment rejected with note.',
                'info'
            )

            return redirect(
                url_for('admin.manage_appointments')
            )

        return render_template(
            'admin/reject_modal.html',
            form=form,
            apt=appointment
        )

    # APPROVED / COMPLETED
    if status in ['Approved', 'Completed']:

        appointment.status = status

        message = (
            f"Your appointment with "
            f"{appointment.officer.name} on "
            f"{appointment.date.strftime('%d %b %Y')} "
            f"at {appointment.time} has been {status}."
        )

        db.session.add(
            Notification(
                user_id=appointment.user_id,
                message=message
            )
        )

        student = db.session.get(
            User,
            appointment.user_id
        )

        db.session.add(
            AppointmentTimeline(
                appointment_id=appointment.id,
                status=status,
                note=f"Status set to {status} by admin."
            )
        )

        from utils import (
            send_email,
            appointment_status_email,
            qr_appointment_email
        )

        if status == 'Approved':

            if not appointment.qr_code_data:

                from app import generate_qr_data

                qr_data, _ = generate_qr_data(
                    appointment.id,
                    secrets.token_urlsafe(16)
                )

                appointment.qr_code_data = qr_data

            from app import generate_qr_data

            _, qr_b64 = generate_qr_data(
                appointment.id,
                appointment.qr_code_data.split('-')[2]
            )

            send_email(
                "Appointment Approved + QR Ticket — IUT",
                [student.email],
                qr_appointment_email(
                    appointment,
                    student,
                    qr_b64
                )
            )

        else:

            send_email(
                f"Appointment {status} — IUT",
                [student.email],
                appointment_status_email(
                    appointment,
                    status
                )
            )

        log_action(
            f'appointment_{status.lower()}',
            f'#{appointment.id} → {status}'
        )

        db.session.commit()

        # SOCKET PUSH
        try:
            from app import push_status_update

            push_status_update(
                appointment.user_id,
                appointment.id,
                status,
                message
            )

        except Exception:
            pass

        flash(
            f'Appointment marked as {status}.',
            'success'
        )

    return redirect(
        request.referrer or
        url_for('admin.manage_appointments')
    )


# ─────────────────────────────────────────────────────────────
# STUDENTS
# ─────────────────────────────────────────────────────────────
@admin_bp.route('/admin/students')
@login_required
@admin_required
def manage_students():

    search = request.args.get('search', '').strip()
    department = request.args.get('department', '').strip()
    status = request.args.get('status', '').strip()

    query = User.query.filter_by(role='student')

    if search:
        query = query.filter(
            db.or_(
                User.name.ilike(f'%{search}%'),
                User.email.ilike(f'%{search}%'),
                User.student_id_num.ilike(f'%{search}%')
            )
        )

    if department:
        query = query.filter(
            User.department.ilike(f'%{department}%')
        )

    if status == 'active':
        query = query.filter_by(is_active=True)

    elif status == 'inactive':
        query = query.filter_by(is_active=False)

    students = query.order_by(
        User.created_at.desc()
    ).all()

    departments = db.session.query(
        User.department
    ).filter(
        User.role == 'student',
        User.department != None
    ).distinct().all()

    departments = [d[0] for d in departments if d[0]]

    return render_template(
        'admin/students.html',
        students=students,
        search=search,
        dept=department,
        status_filter=status,
        departments=departments
    )


# ─────────────────────────────────────────────────────────────
# TOGGLE STUDENT
# ─────────────────────────────────────────────────────────────
@admin_bp.route('/admin/student/<int:user_id>/toggle')
@login_required
@admin_required
def toggle_student(user_id):

    user = db.session.get(User, user_id)

    if user and user.role == 'student':

        user.is_active = not user.is_active

        action = (
            'activated'
            if user.is_active
            else 'deactivated'
        )

        log_action(
            f'student_{action}',
            f'Student {user.name} {action}'
        )

        db.session.commit()

        flash(
            f'Student account {action}.',
            'success'
        )

    return redirect(url_for('admin.manage_students'))


# ─────────────────────────────────────────────────────────────
# STUDENT DETAIL
# ─────────────────────────────────────────────────────────────
@admin_bp.route('/admin/student/<int:user_id>')
@login_required
@admin_required
def student_detail(user_id):

    from flask import abort

    student = db.session.get(User, user_id)

    if not student or student.role != 'student':
        abort(404)

    appointments = Appointment.query.filter_by(
        user_id=user_id
    ).order_by(
        Appointment.date.desc()
    ).all()

    return render_template(
        'admin/student_detail.html',
        student=student,
        appointments=appointments
    )
