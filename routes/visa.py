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

ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def upload_to_cloudinary(file, folder, public_id):
    if not file or not allowed_file(file.filename):
        return None
    try:
        ext = file.filename.rsplit('.', 1)[1].lower()
        resource_type = 'raw' if ext == 'pdf' else 'image'
        result = cloudinary.uploader.upload(
            file,
            folder=f'iut_visa/{folder}',
            public_id=public_id,
            resource_type=resource_type,
            overwrite=True,
            access_mode='public',
        )
        return result.get('secure_url')
    except Exception as e:
        print(f'[IUT] Cloudinary upload error: {e}')
        return None


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

    existing = VisaApplication.query.filter_by(user_id=uid).first()
    if existing and existing.status == 'Pending':
        flash('You already have a pending visa application.', 'warning')
        return redirect(url_for('visa.visa_guide'))

    student_name   = request.form.get('student_name',   current_user.name).strip()
    student_id_num = request.form.get('student_id_num', '').strip()
    department     = request.form.get('department',     '').strip()

    if not student_id_num or not department:
        flash('Student ID and Department are required.', 'danger')
        return redirect(url_for('visa.visa_guide'))

    def up(field):
        f = request.files.get(field)
        if f and f.filename:
            return upload_to_cloudinary(f, f'user_{uid}', f'{field}_{uid}')
        return None

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

    from models import Notification
    db.session.add(Notification(
        user_id = application.user_id,
        message = f'Your visa application has been {status}. {("Note: " + note) if note else ""}'
    ))
    db.session.commit()

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
