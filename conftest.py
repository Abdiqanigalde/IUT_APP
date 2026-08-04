"""
Shared pytest fixtures.

Sets up environment variables BEFORE importing app.py (since app.py reads
config and creates its database tables at import time), points the app at a
throwaway SQLite file for the whole test session, and wipes/recreates all
tables before every single test function so tests never leak state into
each other.
"""
import os
import tempfile

import pytest

# ── Environment must be set before `app` is ever imported ──────────────────────
_db_fd, _DB_PATH = tempfile.mkstemp(suffix='.db')
os.environ['SECRET_KEY']    = 'test-secret-key-not-for-production'
os.environ['DATABASE_URL']  = f'sqlite:///{_DB_PATH}'
os.environ['FLASK_ENV']     = 'testing'
os.environ['CRON_SECRET']   = 'test-cron-secret'
os.environ.pop('BREVO_API_KEY', None)       # unset -> send_email() no-ops instead of trying to send real mail
os.environ.pop('RENDER_EXTERNAL_URL', None)


@pytest.fixture(scope='session')
def app():
    import app as app_module  # noqa: the import itself boots the app + creates tables

    flask_app = app_module.app
    flask_app.config['TESTING'] = True
    flask_app.config['WTF_CSRF_ENABLED'] = False  # tests exercise logic, not CSRF plumbing
    app_module.limiter.enabled = False            # avoid cross-test rate-limit bleed (shared in-memory store)

    yield flask_app

    os.close(_db_fd)
    os.unlink(_DB_PATH)


@pytest.fixture(autouse=True)
def _clean_db(app):
    """Full isolation: every test starts with empty, freshly-created tables."""
    from models import db
    with app.app_context():
        db.drop_all()
        db.create_all()
    yield


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db_session(app):
    from models import db
    with app.app_context():
        yield db.session


# ── User / data factories ───────────────────────────────────────────────────────

@pytest.fixture
def make_user(db_session):
    """Factory fixture: make_user(role='student', **overrides) -> User"""
    from models import User
    from flask_bcrypt import Bcrypt
    bcrypt = Bcrypt()
    created = []

    def _make(role='student', name='Test User', email=None, password='TestPass1',
              email_verified=True, is_active=True, **extra):
        nonlocal created
        email = email or f"{name.lower().replace(' ', '.')}.{len(created)}@iut-dhaka.edu"
        user = User(name=name, email=email,
                    password=bcrypt.generate_password_hash(password).decode('utf-8'),
                    role=role, email_verified=email_verified, is_active=is_active, **extra)
        db_session.add(user)
        db_session.commit()
        created.append(user)
        return user

    return _make


@pytest.fixture
def make_officer(db_session):
    from models import Officer

    def _make(name='Test Officer', designation='Test Designation', is_active=True, **extra):
        officer = Officer(name=name, designation=designation, is_active=is_active, **extra)
        db_session.add(officer)
        db_session.commit()
        return officer

    return _make


@pytest.fixture
def make_appointment(db_session):
    from models import Appointment

    def _make(user, officer, date, status='Pending', time='10:00 AM', **extra):
        apt = Appointment(user_id=user.id, student_name=user.name,
                          student_id_num=extra.pop('student_id_num', 'S0001'),
                          department=extra.pop('department', 'CSE'),
                          officer_id=officer.id, day=date.strftime('%A'), date=date,
                          time=time, issue=extra.pop('issue', 'Test issue'),
                          status=status, **extra)
        db_session.add(apt)
        db_session.commit()
        return apt

    return _make


@pytest.fixture
def login_as(client):
    """Log the test client in as a given user, bypassing the actual login form
    (CSRF is already disabled for tests, but this is simpler and faster for
    tests that aren't specifically testing the login flow itself)."""
    def _login(user):
        with client.session_transaction() as sess:
            sess['_user_id'] = str(user.id)
            sess['_fresh'] = True
        return client

    return _login
