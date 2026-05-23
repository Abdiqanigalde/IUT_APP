"""
Super Admin blueprint — only accessible by users with role='super_admin'.
Handles: creating officer/admin accounts, managing all users, resetting passwords,
activating/deactivating accounts, viewing full audit trail.
"""
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from models import db, User, Officer, AuditLog, Notification, PRIVILEGED_ROLES
from flask_bcrypt import Bcrypt
import secrets
from datetime import datetime, timezone

super_admin_bp = Blueprint('super_admin', __name__, url_prefix='/superadmin')
bcrypt = Bcrypt()

# ── Guard decorator ────────────────────────────────────────────────────────────
def super_admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'super_admin':
            flash('Access denied. Super Admin only.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated

def sa_log(action, detail):
    db.session.add(AuditLog(admin_id=current_user.id, action=action, detail=detail))

# ── Dashboard ──────────────────────────────────────────────────────────────────
@super_admin_bp.route('/')
@login_required
@super_admin_required
def dashboard():
    from models import Appointment
    stats = {
        'total_users': User.query.count(),
        'students':    User.query.filter_by(role='student').count(),
        'officers':    User.query.filter_by(role='officer').count(),
        'admins':      User.query.filter_by(role='admin').count(),
        'super_admins':User.query.filter_by(role='super_admin').count(),
        'inactive':    User.query.filter_by(is_active=False).count(),
        'unverified':  User.query.filter_by(email_verified=False).count(),
        'total_appts': Appointment.query.count(),
    }
    recent_logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(20).all()
    all_users = User.query.order_by(User.created_at.desc()).all()
    return render_template('super_admin/dashboard.html', stats=stats,
                           recent_logs=recent_logs, all_users=all_users)

# ── Create privileged account (officer / admin / super_admin) ─────────────────
@super_admin_bp.route('/create-account', methods=['GET', 'POST'])
@login_required
@super_admin_required
def create_account():
    if request.method == 'POST':
        name  = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        role  = request.form.get('role', '').strip()
        dept  = request.form.get('department', '').strip()
        pwd   = request.form.get('password', '').strip()

        # Validate role — only privileged roles can be created here
        if role not in PRIVILEGED_ROLES:
            flash('Invalid role selected.', 'danger')
            return redirect(url_for('super_admin.create_account'))

        if User.query.filter_by(email=email).first():
            flash('An account with that email already exists.', 'danger')
            return redirect(url_for('super_admin.create_account'))

        if len(pwd) < 8:
            flash('Password must be at least 8 characters.', 'danger')
            return redirect(url_for('super_admin.create_account'))

        hashed = bcrypt.generate_password_hash(pwd).decode('utf-8')
        user = User(
            name=name, email=email, password=hashed,
            role=role, department=dept,
            email_verified=True,   # admin-created accounts are pre-verified
            is_active=True,
        )
        db.session.add(user)

        # If creating an officer account, also create an Officer record
        if role == 'officer':
            officer = Officer(
                name=name,
                designation=request.form.get('designation', 'Officer'),
                email=email
            )
            db.session.add(officer)

        sa_log('create_account', f"Created {role} account: {email} ({name})")
        db.session.commit()
        flash(f'{role.replace("_"," ").title()} account created for {name}.', 'success')
        return redirect(url_for('super_admin.dashboard'))

    return render_template('super_admin/create_account.html')

# ── Toggle active status ───────────────────────────────────────────────────────
@super_admin_bp.route('/toggle/<int:user_id>')
@login_required
@super_admin_required
def toggle_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('super_admin.dashboard'))
    if user.id == current_user.id:
        flash('You cannot deactivate your own account.', 'danger')
        return redirect(url_for('super_admin.dashboard'))
    user.is_active = not user.is_active
    state = 'activated' if user.is_active else 'deactivated'
    sa_log(f'user_{state}', f"{user.name} ({user.email}) [{user.role}] {state}")
    db.session.commit()
    flash(f'Account {state}: {user.name}', 'success')
    return redirect(url_for('super_admin.dashboard'))

# ── Reset any user's password ─────────────────────────────────────────────────
@super_admin_bp.route('/reset-password/<int:user_id>', methods=['POST'])
@login_required
@super_admin_required
def force_reset_password(user_id):
    user = db.session.get(User, user_id)
    new_pwd = request.form.get('new_password', '').strip()
    if not user or len(new_pwd) < 8:
        flash('Invalid user or password too short (min 8 chars).', 'danger')
        return redirect(url_for('super_admin.dashboard'))
    user.password = bcrypt.generate_password_hash(new_pwd).decode('utf-8')
    sa_log('force_password_reset', f"Reset password for {user.name} ({user.email})")
    db.session.commit()
    flash(f'Password reset for {user.name}.', 'success')
    return redirect(url_for('super_admin.dashboard'))

# ── Change role ────────────────────────────────────────────────────────────────
@super_admin_bp.route('/change-role/<int:user_id>', methods=['POST'])
@login_required
@super_admin_required
def change_role(user_id):
    user = db.session.get(User, user_id)
    new_role = request.form.get('role', '').strip()
    from models import VALID_ROLES
    if not user or new_role not in VALID_ROLES:
        flash('Invalid user or role.', 'danger')
        return redirect(url_for('super_admin.dashboard'))
    if user.id == current_user.id:
        flash('Cannot change your own role.', 'danger')
        return redirect(url_for('super_admin.dashboard'))
    old_role = user.role
    user.role = new_role
    sa_log('role_change', f"{user.name}: {old_role} → {new_role}")
    db.session.commit()
    flash(f"Role updated: {user.name} is now {new_role.replace('_',' ').title()}.", 'success')
    return redirect(url_for('super_admin.dashboard'))

# ── Full audit log ─────────────────────────────────────────────────────────────
@super_admin_bp.route('/audit')
@login_required
@super_admin_required
def audit_log():
    logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(500).all()
    return render_template('super_admin/audit_log.html', logs=logs)

# ── Delete user (hard delete) ──────────────────────────────────────────────────
@super_admin_bp.route('/delete/<int:user_id>', methods=['POST'])
@login_required
@super_admin_required
def delete_user(user_id):
    user = db.session.get(User, user_id)
    if not user or user.id == current_user.id:
        flash('Cannot delete this account.', 'danger')
        return redirect(url_for('super_admin.dashboard'))
    sa_log('user_deleted', f"Deleted {user.role} account: {user.email} ({user.name})")
    db.session.delete(user)
    db.session.commit()
    flash(f'Account deleted: {user.name}', 'info')
    return redirect(url_for('super_admin.dashboard'))
