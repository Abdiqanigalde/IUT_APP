from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, timezone
import secrets

db = SQLAlchemy()

# Valid roles — checked on backend to prevent privilege escalation
VALID_ROLES = ('student', 'officer', 'admin', 'super_admin')
# Roles that can ONLY be assigned by super_admin, never by public registration
PRIVILEGED_ROLES = ('officer', 'admin', 'super_admin')


class User(db.Model, UserMixin):
    id              = db.Column(db.Integer, primary_key=True)
    name            = db.Column(db.String(100), nullable=False)
    email           = db.Column(db.String(120), unique=True, nullable=False)
    password        = db.Column(db.String(200), nullable=False)
    role            = db.Column(db.String(20), nullable=False, default='student')
    student_id_num  = db.Column(db.String(50), nullable=True)
    department      = db.Column(db.String(100), nullable=True)
    dark_mode       = db.Column(db.Boolean, default=False)
    is_active       = db.Column(db.Boolean, default=True)
    # ── Email verification ────────────────────────────────────────────────────
    email_verified      = db.Column(db.Boolean, default=False)
    email_verify_token  = db.Column(db.String(64), nullable=True)
    # ── Rate limiting / security ──────────────────────────────────────────────
    failed_logins   = db.Column(db.Integer, default=0)
    locked_until    = db.Column(db.DateTime, nullable=True)
    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at      = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_seen       = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    appointments    = db.relationship('Appointment', backref='student_user', lazy=True)
    notifications   = db.relationship('Notification', backref='user', lazy=True)

    def generate_verify_token(self):
        self.email_verify_token = secrets.token_urlsafe(32)
        return self.email_verify_token

    def is_locked(self):
        if self.locked_until and datetime.now(timezone.utc).replace(tzinfo=None) < self.locked_until:
            return True
        return False


class PasswordResetToken(db.Model):
    """Persistent password reset tokens stored in DB (replaces in-memory dict)."""
    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    token       = db.Column(db.String(64), unique=True, nullable=False, index=True)
    expires_at  = db.Column(db.DateTime, nullable=False)
    used        = db.Column(db.Boolean, default=False)
    created_at  = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    user        = db.relationship('User', backref='reset_tokens')


class Officer(db.Model):
    id              = db.Column(db.Integer, primary_key=True)
    name            = db.Column(db.String(100), nullable=False)
    designation     = db.Column(db.String(100), nullable=False)
    bio             = db.Column(db.Text, nullable=True)
    handles         = db.Column(db.Text, nullable=True)   # comma-separated issues handled
    email           = db.Column(db.String(120), nullable=True)
    room            = db.Column(db.String(50), nullable=True)
    photo_url       = db.Column(db.String(255), nullable=True)
    is_active       = db.Column(db.Boolean, default=True)
    work_start      = db.Column(db.String(5), default="08:00")
    work_end        = db.Column(db.String(5), default="17:00")
    daily_limit     = db.Column(db.Integer, default=0)
    recurring_off_days = db.Column(db.String(20), default="")
    avg_appointment_duration = db.Column(db.Integer, default=15)

    unavailabilities = db.relationship(
        'OfficerUnavailability', backref='officer', lazy=True, cascade='all, delete-orphan'
    )
    working_hours = db.relationship(
        'OfficerWorkingHours', backref='officer', lazy=True, cascade='all, delete-orphan'
    )

    def get_off_days(self):
        if not self.recurring_off_days:
            return []
        return [int(d) for d in self.recurring_off_days.split(',') if d]

    def get_handles(self):
        if not self.handles:
            return []
        return [h.strip() for h in self.handles.split(',') if h.strip()]


class OfficerWorkingHours(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    officer_id  = db.Column(db.Integer, db.ForeignKey('officer.id'), nullable=False)
    weekday     = db.Column(db.Integer, nullable=False)
    start_time  = db.Column(db.String(5), nullable=False)
    end_time    = db.Column(db.String(5), nullable=False)


class OfficerUnavailability(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    officer_id  = db.Column(db.Integer, db.ForeignKey('officer.id'), nullable=False)
    start_date  = db.Column(db.Date, nullable=False)
    end_date    = db.Column(db.Date, nullable=False)
    reason      = db.Column(db.String(255), nullable=False)
    created_at  = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def is_active_on(self, date):
        return self.start_date <= date <= self.end_date


class Appointment(db.Model):
    id              = db.Column(db.Integer, primary_key=True)
    user_id         = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    student_name    = db.Column(db.String(100), nullable=False)
    student_id_num  = db.Column(db.String(50),  nullable=False)
    department      = db.Column(db.String(100),  nullable=False)
    officer_id      = db.Column(db.Integer, db.ForeignKey('officer.id'), nullable=False)
    officer         = db.relationship('Officer', backref='appointments')
    day             = db.Column(db.String(20),  nullable=False)
    date            = db.Column(db.Date,         nullable=False)
    time            = db.Column(db.String(20),   nullable=False)
    issue           = db.Column(db.Text,         nullable=False)
    status          = db.Column(db.String(20),   nullable=False, default='Pending')
    rejection_note  = db.Column(db.Text,         nullable=True)
    reminder_sent   = db.Column(db.Boolean,      default=False)
    created_at      = db.Column(db.DateTime,     default=lambda: datetime.now(timezone.utc))
    priority        = db.Column(db.String(20),   default='Normal')
    queue_number    = db.Column(db.Integer,      nullable=True)
    estimated_wait_time = db.Column(db.Integer,  nullable=True)
    qr_code_data    = db.Column(db.String(255),  nullable=True)
    status_updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )
    # ── Cal.com-style fields ──────────────────────────────────────────────────
    duration        = db.Column(db.Integer,  nullable=True, default=15)   # minutes
    notes           = db.Column(db.Text,     nullable=True)
    meeting_type    = db.Column(db.String(50), nullable=True, default='in_person')  # in_person, online
    timezone        = db.Column(db.String(50), nullable=True, default='Asia/Dhaka')
    location        = db.Column(db.String(255), nullable=True)
    # NOTE: waitlist relationship removed — WaitlistEntry is now slot-based,
    # not appointment-based. Use WaitlistEntry.query.filter_by(officer_id=...,
    # slot_date=..., slot_time=...) directly.


class WaitlistEntry(db.Model):
    """
    Slot-based waitlist entry.

    Keyed on (officer_id, slot_date, slot_time) — NOT on appointment_id —
    so entries survive appointment cancellations and reschedules.

    Migration note: the old `appointment_id` foreign key column has been
    removed. Run the migration script below before deploying.
    """
    __tablename__ = 'waitlist_entry'

    id              = db.Column(db.Integer, primary_key=True)

    # ── Slot identity (replaces appointment_id) ───────────────────────────────
    officer_id      = db.Column(db.Integer, db.ForeignKey('officer.id'), nullable=False, index=True)
    slot_date       = db.Column(db.Date,    nullable=False, index=True)
    slot_time       = db.Column(db.String(30), nullable=False)

    # ── Student info ──────────────────────────────────────────────────────────
    user_id         = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    student_name    = db.Column(db.String(100), nullable=False)
    student_id_num  = db.Column(db.String(50),  nullable=False)
    department      = db.Column(db.String(100),  nullable=False)
    issue           = db.Column(db.Text,         nullable=False)
    joined_at       = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # ── Relationships ─────────────────────────────────────────────────────────
    user    = db.relationship('User',    backref='waitlist_entries')
    officer = db.relationship('Officer', backref='waitlist_entries')

    # ── Unique constraint: one entry per student per slot ─────────────────────
    __table_args__ = (
        db.UniqueConstraint('officer_id', 'slot_date', 'slot_time', 'user_id',
                            name='uq_waitlist_student_slot'),
    )


class Notification(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message     = db.Column(db.String(500), nullable=False)
    is_read     = db.Column(db.Boolean, default=False)
    created_at  = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class NotificationLog(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    type        = db.Column(db.String(50),  nullable=False)   # email, sms, whatsapp
    subject     = db.Column(db.String(255), nullable=True)
    message     = db.Column(db.Text,        nullable=False)
    status      = db.Column(db.String(20),  default='pending')  # pending, sent, failed
    created_at  = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    sent_at     = db.Column(db.DateTime, nullable=True)
    user        = db.relationship('User', backref='notification_logs')


class Feedback(db.Model):
    id              = db.Column(db.Integer, primary_key=True)
    appointment_id  = db.Column(db.Integer, db.ForeignKey('appointment.id'), nullable=False, unique=True)
    student_id      = db.Column(db.Integer, db.ForeignKey('user.id'),     nullable=False)
    officer_id      = db.Column(db.Integer, db.ForeignKey('officer.id'),  nullable=False)
    rating          = db.Column(db.Integer, nullable=False)
    comments        = db.Column(db.Text,    nullable=True)
    created_at      = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    appointment     = db.relationship('Appointment', backref='feedback', uselist=False)
    student         = db.relationship('User',    backref='feedback_given')
    officer         = db.relationship('Officer', backref='feedback_received')


class AppointmentTimeline(db.Model):
    id              = db.Column(db.Integer, primary_key=True)
    appointment_id  = db.Column(db.Integer, db.ForeignKey('appointment.id'), nullable=False)
    status          = db.Column(db.String(50), nullable=False)
    note            = db.Column(db.Text,       nullable=True)
    created_at      = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    appointment     = db.relationship('Appointment', backref='timeline_events')


class AuditLog(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    admin_id    = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    action      = db.Column(db.String(100), nullable=False)
    detail      = db.Column(db.String(500), nullable=False)
    created_at  = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    admin       = db.relationship('User', backref='audit_logs')


# ══════════════════════════════════════════════════════════════════════════════
#  Cal.com-style additions — added for modern booking UI
# ══════════════════════════════════════════════════════════════════════════════

class AppointmentHistory(db.Model):
    """Tracks every status change, reschedule, or action on an appointment."""
    __tablename__ = 'appointment_history'
    id              = db.Column(db.Integer, primary_key=True)
    appointment_id  = db.Column(db.Integer, db.ForeignKey('appointment.id'), nullable=False, index=True)
    action          = db.Column(db.String(50),  nullable=False)   # e.g. 'status_change', 'reschedule', 'note_added'
    old_value       = db.Column(db.Text,        nullable=True)
    new_value       = db.Column(db.Text,        nullable=True)
    changed_by      = db.Column(db.Integer,     db.ForeignKey('user.id'), nullable=True)
    note            = db.Column(db.Text,        nullable=True)
    timestamp       = db.Column(db.DateTime,    default=lambda: datetime.now(timezone.utc))
    appointment     = db.relationship('Appointment', backref='history_events')
    changer         = db.relationship('User',        foreign_keys=[changed_by])
