"""Tests for services/appointment_service.py — the core booking logic used by
every 'book an appointment' flow (student self-service, cal.com-style booking,
admin manual booking). None of this was covered before, despite being the
part of the app most likely to cause double-bookings or silently-wrong queue
numbers if it regresses.
"""
from datetime import date, timedelta
from services.appointment_service import AppointmentService
from models import AppointmentTimeline


# ── check_appointment_conflict ──────────────────────────────────────────────

def test_no_conflict_when_slot_is_free(make_officer):
    officer = make_officer()
    has_conflict, msg = AppointmentService.check_appointment_conflict(
        officer.id, date.today() + timedelta(days=1), '10:00')
    assert has_conflict is False


def test_conflict_when_slot_already_approved(make_user, make_officer, make_appointment):
    officer = make_officer()
    student = make_user(role='student')
    d = date.today() + timedelta(days=1)
    make_appointment(student, officer, d, status='Approved', time='10:00')

    has_conflict, msg = AppointmentService.check_appointment_conflict(officer.id, d, '10:00')
    assert has_conflict is True
    assert 'already booked' in msg.lower()


def test_no_conflict_when_existing_appointment_is_pending_not_approved(
        make_user, make_officer, make_appointment):
    """Regression guard: only 'Approved' appointments should block a slot —
    a merely 'Pending' one shouldn't lock other students out."""
    officer = make_officer()
    student = make_user(role='student')
    d = date.today() + timedelta(days=1)
    make_appointment(student, officer, d, status='Pending', time='10:00')

    has_conflict, _ = AppointmentService.check_appointment_conflict(officer.id, d, '10:00')
    assert has_conflict is False


def test_conflict_when_officer_unavailable(make_officer, db_session):
    from models import OfficerUnavailability
    officer = make_officer()
    d = date.today() + timedelta(days=2)
    db_session.add(OfficerUnavailability(
        officer_id=officer.id, start_date=d, end_date=d, reason='Conference'))
    db_session.commit()

    has_conflict, msg = AppointmentService.check_appointment_conflict(officer.id, d, '10:00')
    assert has_conflict is True
    assert 'Conference' in msg


# ── check_office_hours ──────────────────────────────────────────────────────

def test_within_office_hours_passes(make_officer):
    officer = make_officer(work_start='09:00', work_end='17:00')
    ok, _ = AppointmentService.check_office_hours(officer.id, date.today(), '10:00')
    assert ok is True


def test_before_office_hours_fails(make_officer):
    officer = make_officer(work_start='09:00', work_end='17:00')
    ok, msg = AppointmentService.check_office_hours(officer.id, date.today(), '08:00')
    assert ok is False
    assert 'between' in msg.lower()


def test_at_closing_time_fails(make_officer):
    """work_end is exclusive: booking exactly at close time should be rejected."""
    officer = make_officer(work_start='09:00', work_end='17:00')
    ok, _ = AppointmentService.check_office_hours(officer.id, date.today(), '17:00')
    assert ok is False


def test_recurring_off_day_fails(make_officer):
    officer = make_officer(recurring_off_days='5,6')  # Sat, Sun
    d = date.today()
    while d.weekday() not in (5, 6):
        d += timedelta(days=1)
    ok, msg = AppointmentService.check_office_hours(officer.id, d, '10:00')
    assert ok is False
    assert 'not available' in msg.lower()


# ── check_daily_limit ────────────────────────────────────────────────────────

def test_no_daily_limit_by_default(make_officer):
    officer = make_officer(daily_limit=0)
    ok, msg = AppointmentService.check_daily_limit(officer.id, date.today())
    assert ok is True
    assert 'no daily limit' in msg.lower()


def test_daily_limit_blocks_once_reached(make_user, make_officer, make_appointment):
    officer = make_officer(daily_limit=1)
    student = make_user(role='student')
    d = date.today() + timedelta(days=1)
    make_appointment(student, officer, d, status='Approved', time='09:00')

    ok, msg = AppointmentService.check_daily_limit(officer.id, d)
    assert ok is False
    assert 'daily limit' in msg.lower()


def test_daily_limit_only_counts_approved(make_user, make_officer, make_appointment):
    officer = make_officer(daily_limit=1)
    student = make_user(role='student')
    d = date.today() + timedelta(days=1)
    make_appointment(student, officer, d, status='Pending', time='09:00')

    ok, _ = AppointmentService.check_daily_limit(officer.id, d)
    assert ok is True  # the pending one shouldn't count against the limit


# ── generate_queue_number ────────────────────────────────────────────────────

def test_queue_number_starts_at_one(make_officer):
    officer = make_officer()
    n = AppointmentService.generate_queue_number(officer.id, date.today(), priority='Normal')
    assert n == 1


def test_emergency_always_queues_ahead_of_normal(make_user, make_officer, make_appointment):
    officer = make_officer()
    student = make_user(role='student')
    d = date.today()
    make_appointment(student, officer, d, priority='Normal')
    make_appointment(student, officer, d, priority='Normal')

    # A new Emergency booking should get queue position 1 (ahead of both Normals)
    n = AppointmentService.generate_queue_number(officer.id, d, priority='Emergency')
    assert n == 1

    # A new Normal booking should land after the 2 existing Normals
    n2 = AppointmentService.generate_queue_number(officer.id, d, priority='Normal')
    assert n2 == 3


# ── calculate_estimated_wait_time ───────────────────────────────────────────

def test_wait_time_zero_when_no_earlier_appointments(make_officer):
    officer = make_officer(avg_appointment_duration=15)
    wait = AppointmentService.calculate_estimated_wait_time(officer.id, date.today(), '09:00')
    assert wait == 0


def test_wait_time_scales_with_earlier_approved_appointments(
        make_user, make_officer, make_appointment):
    officer = make_officer(avg_appointment_duration=15)
    student = make_user(role='student')
    d = date.today()
    make_appointment(student, officer, d, status='Approved', time='09:00')
    make_appointment(student, officer, d, status='Approved', time='09:15')
    # A 'Rejected' one at an earlier time shouldn't count towards the wait
    make_appointment(student, officer, d, status='Rejected', time='09:00')

    wait = AppointmentService.calculate_estimated_wait_time(officer.id, d, '09:30')
    assert wait == 30  # 2 earlier approved appointments * 15 min


# ── update_appointment_status ───────────────────────────────────────────────

def test_update_status_persists_and_logs_timeline(
        app, make_user, make_officer, make_appointment):
    officer = make_officer()
    student = make_user(role='student')
    apt = make_appointment(student, officer, date.today(), status='Pending')

    with app.app_context():
        from models import Appointment
        apt = Appointment.query.get(apt.id)
        ok = AppointmentService.update_appointment_status(apt, 'Approved', note='Looks good')
        assert ok is True
        assert apt.status == 'Approved'

        timeline = AppointmentTimeline.query.filter_by(appointment_id=apt.id).all()
        assert any(t.status == 'Approved' and t.note == 'Looks good' for t in timeline)
