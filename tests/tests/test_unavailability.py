"""Tests for admin bulk unavailability and officer self-service unavailability."""
from datetime import date, timedelta
from models import OfficerUnavailability, Appointment


def _next_weekday(target_weekday):
    """Return the next date (today or later) that falls on the given weekday (0=Mon)."""
    d = date.today()
    while d.weekday() != target_weekday:
        d += timedelta(days=1)
    return d


def test_recurring_unavailability_creates_one_period_per_matching_weekday(
        client, login_as, make_user, make_officer):
    admin = make_user(role='admin')
    off1 = make_officer(name='Officer One')
    off2 = make_officer(name='Officer Two')
    login_as(admin)

    wed = _next_weekday(2)  # Wednesday
    r = client.post('/admin/unavailability/bulk', data={
        'officer_ids': [str(off1.id), str(off2.id)],
        'mode': 'recurring',
        'start_date': wed.isoformat(),
        'end_date': (wed + timedelta(days=14)).isoformat(),  # spans 3 Wednesdays
        'recurring_weekday': '2',
        'reason': 'Standing meeting',
    }, follow_redirects=True)
    assert r.status_code == 200

    assert OfficerUnavailability.query.filter_by(officer_id=off1.id).count() == 3
    assert OfficerUnavailability.query.filter_by(officer_id=off2.id).count() == 3


def test_recurring_unavailability_only_cancels_appointments_on_matching_days(
        client, login_as, make_user, make_officer, make_appointment):
    """Regression test for a subtle bug: cancellation logic must check the
    actual occurrence dates, not the whole outer date range — otherwise an
    appointment on an unrelated day of the week gets wrongly cancelled too."""
    admin = make_user(role='admin')
    officer = make_officer()
    student = make_user(role='student')
    login_as(admin)

    wed = _next_weekday(2)
    tue = wed - timedelta(days=1)

    apt_on_pattern    = make_appointment(student, officer, wed, status='Pending')
    apt_off_pattern   = make_appointment(student, officer, tue, status='Pending')

    client.post('/admin/unavailability/bulk', data={
        'officer_ids': [str(officer.id)],
        'mode': 'recurring',
        'start_date': tue.isoformat(),
        'end_date': (wed + timedelta(days=7)).isoformat(),
        'recurring_weekday': '2',  # Wednesday only
        'reason': 'Standing meeting',
    })

    assert Appointment.query.get(apt_on_pattern.id).status == 'Rejected'
    assert Appointment.query.get(apt_off_pattern.id).status == 'Pending', \
        "an appointment on a day NOT matching the recurring pattern must not be cancelled"


def test_officer_can_mark_own_unavailability(client, login_as, make_user, make_officer, db_session):
    officer = make_officer()
    officer_user = make_user(role='officer')
    officer.email = officer_user.email
    db_session.commit()
    login_as(officer_user)

    r = client.post('/officer/unavailability', data={
        'mode': 'range',
        'start_date': date.today().isoformat(),
        'end_date': (date.today() + timedelta(days=3)).isoformat(),
        'recurring_weekday': '0',
        'reason': 'Personal leave',
    }, follow_redirects=True)
    assert r.status_code == 200
    assert OfficerUnavailability.query.filter_by(officer_id=officer.id).count() == 1


def test_officer_cannot_delete_another_officers_unavailability(
        client, login_as, make_user, make_officer, db_session):
    officer_a = make_officer(name='Officer A')
    officer_b = make_officer(name='Officer B')
    officer_a_user = make_user(role='officer', email='officera@iut-dhaka.edu')
    officer_a.email = officer_a_user.email

    period_b = OfficerUnavailability(officer_id=officer_b.id, start_date=date.today(),
                                     end_date=date.today(), reason='Officer B leave')
    db_session.add(period_b)
    db_session.commit()

    login_as(officer_a_user)
    r = client.get(f'/officer/unavailability/delete/{period_b.id}', follow_redirects=True)
    assert b'Not authorized' in r.data
    assert OfficerUnavailability.query.get(period_b.id) is not None, \
        "the other officer's unavailability period must still exist"
