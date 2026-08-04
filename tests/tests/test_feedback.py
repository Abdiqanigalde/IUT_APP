"""Tests for the feedback system (models.Feedback, routes/student.py, admin feedback view)."""
from datetime import date
from models import Feedback


def test_feedback_appointment_relationship_is_scalar_not_list(db_session, make_user, make_officer, make_appointment):
    """Regression test: Feedback.appointment's backref was missing uselist=False,
    which made appointment.feedback return a list instead of a single object and
    crashed the timeline template the moment anyone actually used the feature."""
    student = make_user(role='student')
    officer = make_officer()
    apt = make_appointment(student, officer, date.today(), status='Completed')

    fb = Feedback(appointment_id=apt.id, student_id=student.id, officer_id=officer.id,
                  rating=5, comments='Great!')
    db_session.add(fb)
    db_session.commit()

    db_session.refresh(apt)
    assert apt.feedback is not None
    assert not isinstance(apt.feedback, list), "appointment.feedback must be a single Feedback object, not a list"
    assert apt.feedback.rating == 5


def test_submit_feedback_end_to_end(client, login_as, make_user, make_officer, make_appointment):
    student = make_user(role='student')
    officer = make_officer()
    apt = make_appointment(student, officer, date.today(), status='Completed')
    login_as(student)

    r = client.post('/student/feedback/submit', data={
        'appointment_id': apt.id, 'rating': '4', 'comments': 'Pretty good',
    }, follow_redirects=True)
    assert r.status_code == 200

    fb = Feedback.query.filter_by(appointment_id=apt.id).first()
    assert fb is not None
    assert fb.rating == 4
    assert fb.student_id == student.id
    assert fb.officer_id == officer.id


def test_cannot_submit_feedback_twice(client, login_as, db_session, make_user, make_officer, make_appointment):
    student = make_user(role='student')
    officer = make_officer()
    apt = make_appointment(student, officer, date.today(), status='Completed')
    db_session.add(Feedback(appointment_id=apt.id, student_id=student.id, officer_id=officer.id, rating=5))
    db_session.commit()

    login_as(student)
    client.post('/student/feedback/submit', data={'appointment_id': apt.id, 'rating': '1'})
    assert Feedback.query.filter_by(appointment_id=apt.id).count() == 1, \
        "a second submission for the same appointment must not create a duplicate"


def test_cannot_submit_feedback_for_non_completed_appointment(client, login_as, make_user, make_officer, make_appointment):
    student = make_user(role='student')
    officer = make_officer()
    apt = make_appointment(student, officer, date.today(), status='Pending')
    login_as(student)
    client.post('/student/feedback/submit', data={'appointment_id': apt.id, 'rating': '5'})
    assert Feedback.query.filter_by(appointment_id=apt.id).first() is None


def test_feedback_comment_is_escaped_in_admin_view(client, login_as, db_session,
                                                     make_user, make_officer, make_appointment):
    """A malicious comment must render as inert text, not execute as HTML/JS."""
    admin = make_user(role='admin')
    student = make_user(role='student')
    officer = make_officer()
    apt = make_appointment(student, officer, date.today(), status='Completed')
    db_session.add(Feedback(appointment_id=apt.id, student_id=student.id, officer_id=officer.id,
                            rating=1, comments='<script>alert(1)</script>'))
    db_session.commit()

    login_as(admin)
    r = client.get('/admin/feedback')
    assert b'<script>alert' not in r.data
    assert b'&lt;script&gt;' in r.data


def test_officers_cannot_see_admin_feedback_page(client, login_as, make_user):
    """Per product decision, only admins see feedback — officers should be blocked."""
    officer_user = make_user(role='officer')
    login_as(officer_user)
    r = client.get('/admin/feedback', follow_redirects=True)
    assert b'Student Feedback' not in r.data
