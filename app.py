import os

from flask import Flask, redirect, url_for, render_template, session, request as flask_request
from flask_login import LoginManager, current_user, logout_user
from flask_wtf.csrf import CSRFProtect
from flask_bcrypt import Bcrypt
from flask_mail import Mail
from flask_migrate import Migrate
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_socketio import SocketIO, emit, join_room
from models import db, User
from datetime import datetime, timedelta, timezone

app = Flask(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or 'iut_secret_key_change_in_prod_2026!'
basedir = os.path.abspath(os.path.dirname(__file__))

database_url = os.environ.get(
    'DATABASE_URL',
    'sqlite:///' + os.path.join(basedir, 'database', 'university.db')
)
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql+psycopg://', 1)
if database_url.startswith('postgresql://') and '+' not in database_url:
    database_url = database_url.replace('postgresql://', 'postgresql+psycopg://', 1)

app.config['SQLALCHEMY_DATABASE_URI']        = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle':  300,
}
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)

# ── Flask-Mail ────────────────────────────────────────────────────────────────
app.config['MAIL_SERVER']  = 'smtp-relay.brevo.com'
app.config['MAIL_PORT']    = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_USERNAME']       = os.environ.get('MAIL_USERNAME', '')
app.config['MAIL_PASSWORD']       = os.environ.get('MAIL_PASSWORD', '')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_USERNAME', 'noreply@iut-dhaka.edu')

# ── Extensions ────────────────────────────────────────────────────────────────
csrf     = CSRFProtect(app)
db.init_app(app)
migrate  = Migrate(app, db)
bcrypt   = Bcrypt(app)
mail     = Mail(app)
socketio = SocketIO(app, cors_allowed_origins='*', async_mode='threading')

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "60 per hour"],
    storage_uri="memory://",
)

login_manager = LoginManager(app)
login_manager.login_view             = 'auth.login'
login_manager.login_message_category = 'info'

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

@app.teardown_appcontext
def shutdown_session(exception=None):
    if exception:
        db.session.rollback()
    db.session.remove()


# ── DB init + auto-migrations ─────────────────────────────────────────────────
with app.app_context():
    db_dir = os.path.join(basedir, 'database')
    os.makedirs(db_dir, exist_ok=True)
    db.create_all()

    # ── Auto-create super_admin if none exists ────────────────────────────────
    if not User.query.filter_by(role='super_admin').first():
        from flask_bcrypt import Bcrypt as _B
        _b = _B()
        sa = User(
            name='Super Admin',
            email='superadmin@iut-dhaka.edu',
            password=_b.generate_password_hash('SuperAdmin@2026!').decode('utf-8'),
            role='super_admin',
            email_verified=True,
            is_active=True,
        )
        db.session.add(sa)
        db.session.commit()
        print('[IUT] Default super_admin created: superadmin@iut-dhaka.edu / SuperAdmin@2026!')

    # ── WaitlistEntry migration: appointment_id → slot-based ─────────────────
    try:
        from sqlalchemy import text, inspect as sa_inspect
        inspector  = sa_inspect(db.engine)
        cols       = {c['name'] for c in inspector.get_columns('waitlist_entry')}
        is_pg      = 'postgresql' in str(db.engine.url)

        if 'officer_id' in cols:
            print('[IUT] WaitlistEntry already migrated — skipping.')

        elif 'appointment_id' in cols:
            print('[IUT] Migrating WaitlistEntry to slot-based schema…')
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE waitlist_entry ADD COLUMN officer_id INTEGER"))
                conn.execute(text("ALTER TABLE waitlist_entry ADD COLUMN slot_date DATE"))
                conn.execute(text("ALTER TABLE waitlist_entry ADD COLUMN slot_time VARCHAR(30)"))
                conn.commit()

                if is_pg:
                    conn.execute(text("""
                        UPDATE waitlist_entry we
                        SET  officer_id = a.officer_id,
                             slot_date  = a.date,
                             slot_time  = a.time
                        FROM appointment a
                        WHERE a.id = we.appointment_id
                    """))
                else:
                    conn.execute(text("""
                        UPDATE waitlist_entry
                        SET officer_id = (
                                SELECT officer_id FROM appointment
                                WHERE appointment.id = waitlist_entry.appointment_id),
                            slot_date  = (
                                SELECT date FROM appointment
                                WHERE appointment.id = waitlist_entry.appointment_id),
                            slot_time  = (
                                SELECT time FROM appointment
                                WHERE appointment.id = waitlist_entry.appointment_id)
                        WHERE appointment_id IS NOT NULL
                    """))
                conn.commit()

                deleted = conn.execute(text(
                    "DELETE FROM waitlist_entry WHERE officer_id IS NULL"
                )).rowcount
                if deleted:
                    print(f'[IUT] Removed {deleted} orphaned waitlist entries.')
                conn.commit()

                if is_pg:
                    conn.execute(text("ALTER TABLE waitlist_entry DROP COLUMN IF EXISTS appointment_id"))
                    conn.execute(text("""
                        ALTER TABLE waitlist_entry
                        ADD CONSTRAINT uq_waitlist_student_slot
                        UNIQUE (officer_id, slot_date, slot_time, user_id)
                    """))
                else:
                    conn.execute(text("""
                        CREATE TABLE waitlist_entry_new (
                            id             INTEGER PRIMARY KEY,
                            officer_id     INTEGER NOT NULL REFERENCES officer(id),
                            slot_date      DATE    NOT NULL,
                            slot_time      VARCHAR(30) NOT NULL,
                            user_id        INTEGER NOT NULL REFERENCES user(id),
                            student_name   VARCHAR(100) NOT NULL,
                            student_id_num VARCHAR(50)  NOT NULL,
                            department     VARCHAR(100) NOT NULL,
                            issue          TEXT    NOT NULL,
                            joined_at      DATETIME,
                            UNIQUE (officer_id, slot_date, slot_time, user_id)
                        )
                    """))
                    conn.execute(text("""
                        INSERT INTO waitlist_entry_new
                            (id, officer_id, slot_date, slot_time, user_id,
                             student_name, student_id_num, department, issue, joined_at)
                        SELECT
                            id, officer_id, slot_date, slot_time, user_id,
                            student_name, student_id_num, department, issue, joined_at
                        FROM waitlist_entry
                        WHERE officer_id IS NOT NULL
                    """))
                    conn.execute(text("DROP TABLE waitlist_entry"))
                    conn.execute(text("ALTER TABLE waitlist_entry_new RENAME TO waitlist_entry"))
                conn.commit()

            print('[IUT] WaitlistEntry migration complete ✅')

        else:
            print('[IUT] WaitlistEntry table is new — no migration needed.')

    except Exception as _mig_err:
        print(f'[IUT] WaitlistEntry migration error (non-fatal): {_mig_err}')

    # ── Cal.com migration: new columns + appointment_history table ────────────
    try:
        from sqlalchemy import text, inspect as sa_inspect2
        inspector2 = sa_inspect2(db.engine)
        is_pg2     = 'postgresql' in str(db.engine.url)

        apt_cols = {c['name'] for c in inspector2.get_columns('appointment')}
        new_cols = {
            'duration':     'INTEGER DEFAULT 15',
            'notes':        'TEXT',
            'meeting_type': "VARCHAR(50) DEFAULT 'in_person'",
            'timezone':     "VARCHAR(50) DEFAULT 'Asia/Dhaka'",
            'location':     'VARCHAR(255)',
        }
        with db.engine.connect() as conn:
            for col, definition in new_cols.items():
                if col not in apt_cols:
                    conn.execute(text(f'ALTER TABLE appointment ADD COLUMN {col} {definition}'))
                    print(f'[IUT] Cal.com migration: added appointment.{col}')
            conn.commit()

        all_tables = inspector2.get_table_names()
        if 'appointment_history' not in all_tables:
            with db.engine.connect() as conn:
                if is_pg2:
                    conn.execute(text('''
                        CREATE TABLE appointment_history (
                            id             SERIAL PRIMARY KEY,
                            appointment_id INTEGER NOT NULL REFERENCES appointment(id),
                            action         VARCHAR(50) NOT NULL,
                            old_value      TEXT,
                            new_value      TEXT,
                            changed_by     INTEGER REFERENCES "user"(id),
                            note           TEXT,
                            timestamp      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    '''))
                else:
                    conn.execute(text('''
                        CREATE TABLE appointment_history (
                            id             INTEGER PRIMARY KEY AUTOINCREMENT,
                            appointment_id INTEGER NOT NULL REFERENCES appointment(id),
                            action         VARCHAR(50) NOT NULL,
                            old_value      TEXT,
                            new_value      TEXT,
                            changed_by     INTEGER REFERENCES user(id),
                            note           TEXT,
                            timestamp      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    '''))
                conn.commit()
            print('[IUT] Cal.com migration: created appointment_history table ✅')
        else:
            print('[IUT] Cal.com migration: appointment_history already exists — skipping.')

    except Exception as _calcom_err:
        print(f'[IUT] Cal.com migration error (non-fatal): {_calcom_err}')

    # ── officer_id nullable migration ─────────────────────────────────────────
    try:
        from sqlalchemy import text, inspect as sa_inspect3
        inspector3 = sa_inspect3(db.engine)
        is_pg3     = 'postgresql' in str(db.engine.url)

        if is_pg3:
            with db.engine.connect() as conn:
                # Check if the NOT NULL constraint still exists
                result = conn.execute(text("""
                    SELECT is_nullable
                    FROM information_schema.columns
                    WHERE table_name = 'appointment'
                    AND column_name  = 'officer_id'
                """)).fetchone()

                if result and result[0] == 'NO':
                    conn.execute(text(
                        'ALTER TABLE appointment ALTER COLUMN officer_id DROP NOT NULL'
                    ))
                    conn.commit()
                    print('[IUT] officer_id nullable migration: done ✅')
                else:
                    print('[IUT] officer_id nullable migration: already applied — skipping.')
        else:
            # SQLite doesn't enforce NOT NULL changes easily, but db.create_all()
            # won't re-add it since the model now has nullable=True
            print('[IUT] officer_id nullable migration: SQLite — skipping (handled by model).')

    except Exception as _nullable_err:
        print(f'[IUT] officer_id nullable migration error (non-fatal): {_nullable_err}')


# ── Session timeout ───────────────────────────────────────────────────────────
@app.before_request
def check_session_timeout():
    if current_user.is_authenticated:
        last = session.get('last_activity')
        now  = datetime.now(timezone.utc).timestamp()
        if last and (now - last) > 30 * 60:
            logout_user()
            session.clear()
            from flask import flash
            flash('Session expired due to inactivity.', 'warning')
            return redirect(url_for('auth.login'))
        session['last_activity'] = now
        session.permanent = True


# ── Time slot generator ───────────────────────────────────────────────────────
def generate_time_slots(start_str="08:00", end_str="17:00"):
    slots, fmt = [], "%H:%M"
    current    = datetime.strptime(start_str, fmt)
    end        = datetime.strptime(end_str,   fmt)
    while current < end:
        nxt = current + timedelta(hours=1)
        slots.append(f"{current.strftime('%I:%M %p')} - {nxt.strftime('%I:%M %p')}")
        current = nxt
    return slots


# ── QR code generator ─────────────────────────────────────────────────────────
def generate_qr_data(appointment_id, token):
    import io, base64
    data = f"APT-{appointment_id}-{token}"
    try:
        import qrcode
        qr = qrcode.QRCode(version=1, box_size=8, border=2)
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        b64 = base64.b64encode(buf.getvalue()).decode()
    except ImportError:
        try:
            from PIL import Image, ImageDraw
            img  = Image.new('RGB', (200, 200), color='white')
            draw = ImageDraw.Draw(img)
            draw.rectangle([10, 10, 190, 190], outline='black', width=3)
            draw.text((20, 90), data[:20], fill='black')
            buf  = io.BytesIO()
            img.save(buf, format='PNG')
            b64  = base64.b64encode(buf.getvalue()).decode()
        except ImportError:
            b64 = ""
    return data, b64


# ── Socket.IO events ──────────────────────────────────────────────────────────
@socketio.on('join')
def on_join(data):
    room = str(data.get('user_id', ''))
    if room:
        join_room(room)

def push_status_update(user_id, appointment_id, status, message):
    socketio.emit('appointment_update', {
        'appointment_id': appointment_id,
        'status':         status,
        'message':        message,
        'timestamp':      datetime.now(timezone.utc).isoformat(),
    }, room=str(user_id))


# ── Error handlers ────────────────────────────────────────────────────────────
@app.errorhandler(404)
def not_found(e):    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def server_error(e): return render_template('errors/500.html'), 500

@app.errorhandler(403)
def forbidden(e):    return render_template('errors/403.html'), 403

@app.errorhandler(429)
def rate_limited(e): return render_template('errors/429.html'), 429


# ── Blueprints ────────────────────────────────────────────────────────────────
from routes.auth        import auth_bp
from routes.student     import student_bp
from routes.admin       import admin_bp
from routes.officer     import officer_bp
from routes.super_admin import super_admin_bp

app.register_blueprint(auth_bp)
app.register_blueprint(student_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(officer_bp)
app.register_blueprint(super_admin_bp)

limiter.limit("10 per minute")(auth_bp)


# ── Root route ────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    if current_user.is_authenticated:
        role = current_user.role
        if role == 'super_admin': return redirect(url_for('super_admin.dashboard'))
        if role == 'admin':       return redirect(url_for('admin.dashboard'))
        if role == 'officer':     return redirect(url_for('officer.dashboard'))
        return redirect(url_for('student.dashboard'))
    return render_template('home.html')


# ── Live notifications API ────────────────────────────────────────────────────
@app.route('/api/notifications/unread-count')
def unread_count():
    from models import Notification
    if not current_user.is_authenticated:
        return {'count': 0}
    try:
        count = Notification.query.filter_by(
            user_id=current_user.id, is_read=False
        ).count()
        return {'count': count}
    except Exception:
        db.session.rollback()
        return {'count': 0}


if __name__ == '__main__':
    port  = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'development'
    socketio.run(app, host='0.0.0.0', port=port, debug=debug, allow_unsafe_werkzeug=True)
