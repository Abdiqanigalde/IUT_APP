"""Tests for the cron-triggered reminders endpoint (routes/admin.py)."""
from datetime import date, timedelta
from models import Appointment


def test_cron_reminders_rejects_missing_secret(client):
    r = client.post('/admin/cron/send-reminders')
    assert r.status_code == 401


def test_cron_reminders_rejects_wrong_secret(client):
    r = client.post('/admin/cron/send-reminders', headers={'X-Cron-Secret': 'wrong'})
    assert r.status_code == 401


def test_cron_reminders_sends_and_is_idempotent(client, make_user, make_officer, make_appointment):
    officer = make_officer()
    student = make_user(role='student')
    tomorrow = date.today() + timedelta(days=1)
    make_appointment(student, officer, tomorrow, status='Approved')

    r1 = client.post('/admin/cron/send-reminders', headers={'X-Cron-Secret': 'test-cron-secret'})
    assert r1.status_code == 200
    assert r1.get_json()['reminders_sent'] == 1

    r2 = client.post('/admin/cron/send-reminders', headers={'X-Cron-Secret': 'test-cron-secret'})
    assert r2.get_json()['reminders_sent'] == 0, "must not re-send a reminder that was already sent"


def test_cron_reminders_only_targets_approved_appointments_tomorrow(
        client, make_user, make_officer, make_appointment):
    officer = make_officer()
    student = make_user(role='student')
    tomorrow = date.today() + timedelta(days=1)
    next_week = date.today() + timedelta(days=7)

    make_appointment(student, officer, tomorrow, status='Pending')     # wrong status
    make_appointment(student, officer, next_week, status='Approved')   # wrong date

    r = client.post('/admin/cron/send-reminders', headers={'X-Cron-Secret': 'test-cron-secret'})
    assert r.get_json()['reminders_sent'] == 0
