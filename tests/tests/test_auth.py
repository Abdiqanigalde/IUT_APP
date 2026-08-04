"""Tests for routes/auth.py — registration, login gating, password reset."""
from models import User


def test_register_creates_unverified_user(client, db_session):
    r = client.post('/register', data={
        'name': 'New Student', 'email': 'newstudent@iut-dhaka.edu',
        'password': 'StrongPass1', 'confirm_password': 'StrongPass1', 'role': 'student',
    }, follow_redirects=True)
    assert r.status_code == 200
    user = User.query.filter_by(email='newstudent@iut-dhaka.edu').first()
    assert user is not None
    assert user.email_verified is False, "email_verified must default to False so verification is actually enforced"


def test_login_blocked_when_email_unverified(client, make_user):
    make_user(role='student', email='unverified@iut-dhaka.edu',
              password='StrongPass1', email_verified=False)
    r = client.post('/login', data={'email': 'unverified@iut-dhaka.edu', 'password': 'StrongPass1'},
                    follow_redirects=True)
    assert b'verify your email' in r.data.lower()
    with client.session_transaction() as sess:
        assert '_user_id' not in sess, "unverified user must not actually be logged in"


def test_login_succeeds_when_email_verified(client, make_user):
    make_user(role='student', email='verified@iut-dhaka.edu',
              password='StrongPass1', email_verified=True)
    r = client.post('/login', data={'email': 'verified@iut-dhaka.edu', 'password': 'StrongPass1'})
    assert r.status_code == 302
    with client.session_transaction() as sess:
        assert '_user_id' in sess


def test_weak_password_rejected_on_registration(client, db_session):
    r = client.post('/register', data={
        'name': 'Weak Pw', 'email': 'weakpw@iut-dhaka.edu',
        'password': 'weak', 'confirm_password': 'weak', 'role': 'student',
    })
    assert r.status_code == 200  # re-renders form with error, does not redirect
    user = User.query.filter_by(email='weakpw@iut-dhaka.edu').first()
    assert user is None, "account must not be created when password fails the strength policy"


def test_forgot_password_never_leaks_reset_link_in_response(client, make_user):
    """Regression test for the original account-takeover bug: the reset link
    used to be flashed directly on the page when email wasn't configured."""
    make_user(role='student', email='resettest@iut-dhaka.edu')
    r = client.post('/forgot-password', data={'email': 'resettest@iut-dhaka.edu'}, follow_redirects=True)
    assert b'reset-password/' not in r.data, "reset token/link must never appear in the HTTP response"


def test_forgot_password_gives_same_response_for_nonexistent_email(client):
    """The response shouldn't reveal whether an email is registered (user enumeration)."""
    r1 = client.post('/forgot-password', data={'email': 'doesnotexist@iut-dhaka.edu'}, follow_redirects=True)
    assert b'If that email is registered' in r1.data
