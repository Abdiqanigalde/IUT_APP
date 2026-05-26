import os
import cloudinary
import cloudinary.uploader
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from models import db, VisaApplication, User
from datetime import datetime, timezone

visa_bp = Blueprint('visa', __name__)

cloudinary.config(
    cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME'),
    api_key    = os.environ.get('CLOUDINARY_API_KEY'),
    api_secret = os.environ.get('CLOUDINARY_API_SECRET'),
)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def upload_to_cloudinary(file, folder, public_id):
    if not file or not allowed_file(file.filename):
        return None
    try:
        result = cloudinary.uploader.upload(
            file,
            folder=f'iut_visa/{folder}',
            public_id=public_id,
            resource_type='image',
            overwrite=True,
            access_mode='public',
        )
        return result.get('secure_url')
    except Exception as e:
        print(f'[IUT] Cloudinary upload error: {e}')
        return None


def send_visa_email(student, status, note=''):
    """Send email to student when visa application status changes."""
    try:
        from utils import send_email

        if status == 'Approved':
            subject = '✅ Visa Application Approved — IUT'
            body = f"""
            <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">
              <div style="background:linear-gradient(135deg,#0d4f3c,#1a7a5e);padding:32px;border-radius:12px 12px 0 0;text-align:center;">
                <h1 style="color:white;margin:0;font-size:1.6rem;">✅ Application Approved!</h1>
              </div>
              <div style="background:#f9fafb;padding:28px;border-radius:0 0 12px 12px;border:1px solid #e5e7eb;">
                <p style="font-size:1rem;color:#374151;">Dear <strong>{student.name}</strong>,</p>
                <p style="color:#374151;">Congratulations! Your visa document application has been <strong style="color:#16a34a;">approved</strong> by the visa officer.</p>
                {"<div style='background:#f0fdf4;border-left:4px solid #22c55e;padding:12px 16px;border-radius:6px;margin:16px 0;'><strong>Officer Note:</strong> " + note + "</div>" if note else ""}
                <p style="color:#374151;">You may now proceed with the next steps of your visa application process.</p>
                <div style="text-align:center;margin-top:24px;">
                  <a href="https://iut-app.onrender.com/student/visa-guide"
                     style="background:#0d4f3c;color:white;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:600;">
                    View Application
                  </a>
                </div>
                <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0;">
                <p style="color:#9ca3af;font-size:.82rem;text-align:center;">IUT University Appointment Management System</p>
              </div>
            </div>
            """

        elif status == 'Rejected':
            subject = '❌ Visa Application Rejected — IUT'
            body = f"""
            <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">
              <div style="background:linear-gradient(135deg,#991b1b,#dc2626);padding:32px;border-radius:12px 12px 0 0;text-align:center;">
                <h1 style="color:white;margin:0;font-size:1.6rem;">❌ Application Rejected</h1>
              </div>
              <div style="background:#f9fafb;padding:28px;border-radius:0 0 12px 12px;border:1px solid #e5e7eb;">
                <p style="font-size:1rem;color:#374151;">Dear <strong>{student.name}</strong>,</p>
                <p style="color:#374151;">Unfortunately, your visa document application has been <strong style="color:#dc2626;">rejected</strong> by the visa officer.</p>
                {"<div style='background:#fef2f2;border-left:4px solid #ef4444;padding:12px 16px;border-radius:6px;margin:16px 0;'><strong>Reason:</strong> " + note + "</div>" if note else ""}
                <p style="color:#374151;">Please log in to review the feedback, correct your documents, and resubmit your application.</p>
                <div style="text-align:center;margin-top:24px;">
                  <a href="https://iut-app.onrender.com/student/visa-guide"
                     style="background:#dc2626;color:white;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:600;">
                    Resubmit Application
                  </a>
                </div>
                <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0;">
                <p style="color:#9ca3af;font-size:.82rem;text-align:center;">IUT University Appointment Management System</p>
              </div>
            </div>
            """
        else:
            return

        send_email(subject, [student.email], body)
        print(f'[IUT] Visa email sent to {student.email} — {status}')

    except Exception as e:
        print(f'[IUT] Visa email error: {e}')


@visa_bp.route('/student/visa-guide')
@login_required
def visa_guide():
    if current_user.role != 'student':
        return redirect(url_for('index'))
    existing = VisaApplication.query.filter_by(user_id=current_user.id)\
                .order_by(VisaApplication.created_at.desc()).first()
    return render_template('student/visa_guide.html', application=existing)


@visa_bp.route('/student/visa/submit', methods=['POST'])
@login_required
def visa_submit():
    if current_user.role != 'student':
        return redirect(url_for('index'))

    uid = current_user.id

    existing = VisaApplication.query.filter_by(user_id=uid)\
                .order_by(VisaApplication.created_at.desc()).first()

    if existing and existing.status in ('Pending', 'Approved'):
        flash('You already have an active visa application.', 'warning')
        return redirect(url_for('visa.visa_guide'))

    student_name   = request.form.get('student_name',   current_user.name).strip()
    student_id_num = request.form.get('student_id_num', '').strip()
    department     = request.form.get('department',     '').strip()

    if not student_id_num or not department:
        flash('Student ID and Department are required.', 'danger')
        return redirect(url_for('visa.visa_guide'))

    def up(field, old_url=None):
        f = request.files.get(field)
        if f and f.filename:
            return upload_to_cloudinary(f, f'user_{uid}', f'{field}_{uid}')
        return old_url

    if existing and existing.status == 'Rejected':
        existing.student_name   = student_name
        existing.student_id_num = student_id_num
        existing.department     = department
        existing.status         = 'Pending'
        existing.officer_note   = None
        existing.updated_at     = datetime.now(timezone.utc)
        existing.passport_copy  = up('passport_copy',  existing.passport_copy)
        existing.photo          = up('photo',          existing.photo)
        existing.offer_letter   = up('offer_letter',   existing.offer_letter)
        existing.student_id_doc = up('student_id_doc', existing.student_id_doc)
        existing.expired_visa   = up('expired_visa',   existing.expired_visa)
        existing.grade_sheet    = up('grade_sheet',    existing.grade_sheet)
        existing.on_arrival     = up('on_arrival',     existing.on_arrival)
        db.session.commit()
        flash('Application resubmitted successfully! The visa officer will review it.', 'success')

    else:
        app_obj = VisaApplication(
            user_id        = uid,
            student_name   = student_name,
            student_id_num = student_id_num,
            department     = department,
            status         = 'Pending',
            passport_copy  = up('passport_copy'),
            photo          = up('photo'),
            offer_letter   = up('offer_letter'),
            student_id_doc = up('student_id_doc'),
            expired_visa   = up('expired_visa'),
            grade_sheet    = up('grade_sheet'),
            on_arrival     = up('on_arrival'),
        )
        db.session.add(app_obj)
        db.session.commit()
        flash('Visa documents submitted successfully! The visa officer will review them.', 'success')

    return redirect(url_for('visa.visa_guide'))


@visa_bp.route('/visa-officer/dashboard')
@login_required
def visa_officer_dashboard():
    if current_user.role != 'visa_officer':
        return redirect(url_for('index'))
    applications = VisaApplication.query.order_by(VisaApplication.created_at.desc()).all()
    return render_template('visa_officer/dashboard.html', applications=applications)


@visa_bp.route('/visa-officer/application/<int:app_id>')
@login_required
def visa_application_detail(app_id):
    if current_user.role != 'visa_officer':
        return redirect(url_for('index'))
    application = db.session.get(VisaApplication, app_id)
    if not application:
        flash('Application not found.', 'danger')
        return redirect(url_for('visa.visa_officer_dashboard'))
    return render_template('visa_officer/application_detail.html', application=application)


@visa_bp.route('/visa-officer/application/<int:app_id>/update', methods=['POST'])
@login_required
def visa_update_status(app_id):
    if current_user.role != 'visa_officer':
        return redirect(url_for('index'))
    application = db.session.get(VisaApplication, app_id)
    if not application:
        flash('Application not found.', 'danger')
        return redirect(url_for('visa.visa_officer_dashboard'))

    status = request.form.get('status', '').strip()
    note   = request.form.get('officer_note', '').strip()

    if status not in ('Approved', 'Rejected', 'Pending'):
        flash('Invalid status.', 'danger')
        return redirect(url_for('visa.visa_application_detail', app_id=app_id))

    application.status       = status
    application.officer_note = note
    application.updated_at   = datetime.now(timezone.utc)
    db.session.commit()

    # In-app notification
    from models import Notification
    db.session.add(Notification(
        user_id = application.user_id,
        message = f'Your visa application has been {status}. {("Note: " + note) if note else ""}'
    ))
    db.session.commit()

    # Email notification (only for Approved/Rejected)
    if status in ('Approved', 'Rejected'):
        student = db.session.get(User, application.user_id)
        if student:
            send_visa_email(student, status, note)

    flash(f'Application {status} successfully.', 'success')
    return redirect(url_for('visa.visa_officer_dashboard'))


@visa_bp.route('/visa-officer/application/<int:app_id>/delete', methods=['POST'])
@login_required
def visa_delete_application(app_id):
    if current_user.role != 'visa_officer':
        return redirect(url_for('index'))
    application = db.session.get(VisaApplication, app_id)
    if application:
        db.session.delete(application)
        db.session.commit()
        flash('Application deleted.', 'success')
    return redirect(url_for('visa.visa_officer_dashboard'))
