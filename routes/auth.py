from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from models import db, User, PasswordResetToken, PRIVILEGED_ROLES
from forms import RegistrationForm, LoginForm, ForgotPasswordForm, ResetPasswordForm
from flask_bcrypt import Bcrypt
import secrets
from datetime import datetime, timedelta, timezone

auth_bp = Blueprint('auth', __name__)
bcrypt = Bcrypt()

# ── Registration ───────────────────────────────────────────────────────────────
@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = RegistrationForm()
    if form.validate_on_submit():
        # ── SECURITY: Force role to 'student' regardless of submitted value ──
        # This prevents any manual API tampering to gain privileged roles.
        submitted_role = form.role.data
        if submitted_role in PRIVILEGED_ROLES:
            flash('Invalid role selected. Public registration only allows student accounts.', 'danger')
            return render_template('register.html', title='Register', form=form)

        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        user = User(
            name=form.name.data,
            email=form.email.data,
            password=hashed_password,
            role='student',           # always 'student' for public registration
            email_verified=True,
        )
        user.generate_verify_token()
        db.session.add(user)
        db.session.commit()

        # Send verification email
        from utils import send_email, email_verification_email
        verify_url = url_for('auth.verify_email', token=user.email_verify_token, _external=True)
        send_email('Verify your IUT email', [user.email], email_verification_email(user, verify_url))

        flash('Account created! Please check your email to verify your account before logging in.', 'success')
        return redirect(url_for('auth.login'))
    return render_template('register.html', title='Register', form=form)

# ── Email verification ─────────────────────────────────────────────────────────
@auth_bp.route('/verify-email/<token>')
def verify_email(token):
    user = User.query.filter_by(email_verify_token=token).first()
    if not user:
        flash('Invalid or expired verification link.', 'danger')
        return redirect(url_for('auth.login'))
    if user.email_verified:
        flash('Email already verified. Please log in.', 'info')
        return redirect(url_for('auth.login'))
    user.email_verified = True
    user.email_verify_token = None
    db.session.commit()
    flash('Email verified! You can now log in.', 'success')
    return redirect(url_for('auth.login'))

# ── Login (with account lockout after 5 failed attempts) ──────────────────────
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()

        # Account lockout guard
        if user and user.is_locked():
            mins_left = int((user.locked_until - datetime.utcnow()).total_seconds() / 60) + 1  # naive: SQLite stores naive UTC
            flash(f'Account temporarily locked due to too many failed attempts. Try again in {mins_left} minute(s).', 'danger')
            return render_template('login.html', title='Login', form=form)

        if user and bcrypt.check_password_hash(user.password, form.password.data):
            if not user.is_active:
                flash('Your account has been deactivated. Contact an administrator.', 'danger')
                return render_template('login.html', title='Login', form=form)
            if not user.email_verified:
                user.email_verified = True
                db.session.commit()
            # Reset failed logins on success
            user.failed_logins = 0
            user.locked_until = None
            db.session.commit()
            login_user(user, remember=form.remember.data if hasattr(form, 'remember') else False)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('index'))
        else:
            if user:
                user.failed_logins = (user.failed_logins or 0) + 1
                if user.failed_logins >= 5:
                    user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
                    flash('Too many failed attempts. Account locked for 15 minutes.', 'danger')
                else:
                    remaining = 5 - user.failed_logins
                    flash(f'Login failed. {remaining} attempt(s) remaining before lockout.', 'danger')
                db.session.commit()
            else:
                flash('Login unsuccessful. Please check your email and password.', 'danger')
    return render_template('login.html', title='Login', form=form)

# ── Logout ────────────────────────────────────────────────────────────────────
@auth_bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('auth.login'))

# ── Forgot password (persistent tokens) ───────────────────────────────────────
@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            # Invalidate previous tokens for this user
            PasswordResetToken.query.filter_by(user_id=user.id, used=False).update({'used': True})
            token_str = secrets.token_urlsafe(32)
            prt = PasswordResetToken(
                user_id=user.id,
                token=token_str,
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
            )
            db.session.add(prt)
            db.session.commit()
            reset_url = url_for('auth.reset_password', token=token_str, _external=True)
            from utils import send_email, password_reset_email
            from flask import current_app
            mail_configured = bool(current_app.config.get('MAIL_USERNAME'))
            if mail_configured:
                send_email('Password Reset — IUT Appointments', [user.email],
                           password_reset_email(user, reset_url))
                flash('A password reset link has been sent to your email address.', 'info')
            else:
                # No email configured — show the link directly so user can proceed
                flash(
                    f'Email service is not configured. Use this link to reset your password '
                    f'(valid for 1 hour): <a href="{reset_url}" class="alert-link">Click here to reset your password</a>',
                    'warning'
                )
        else:
            flash('If that email is registered, a reset link has been sent.', 'info')
        return redirect(url_for('auth.forgot_password'))
    return render_template('forgot_password.html', title='Forgot Password', form=form)

# ── Reset password ─────────────────────────────────────────────────────────────
@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    prt = PasswordResetToken.query.filter_by(token=token, used=False).first()
    if not prt or datetime.now(timezone.utc) > prt.expires_at:
        flash('Invalid or expired reset link.', 'danger')
        return redirect(url_for('auth.forgot_password'))
    user = db.session.get(User, prt.user_id)
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('auth.forgot_password'))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.password = bcrypt.generate_password_hash(form.new_password.data).decode('utf-8')
        prt.used = True
        db.session.commit()
        flash('Password reset successfully! Please log in.', 'success')
        return redirect(url_for('auth.login'))
    return render_template('reset_password.html', title='Reset Password', form=form)

# ── Resend verification ────────────────────────────────────────────────────────
@auth_bp.route('/resend-verification', methods=['POST'])
def resend_verification():
    email = request.form.get('email', '').strip()
    user = User.query.filter_by(email=email).first()
    if user and not user.email_verified:
        user.generate_verify_token()
        db.session.commit()
        from utils import send_email, email_verification_email
        verify_url = url_for('auth.verify_email', token=user.email_verify_token, _external=True)
        send_email('Verify your IUT email', [user.email], email_verification_email(user, verify_url))
    flash('If that address is registered and unverified, a new link has been sent.', 'info')
    return redirect(url_for('auth.login'))
