"""Tests for routes/admin.py appointment list: search, filters, CSV export, pagination."""
from datetime import date, timedelta
from utils import csv_safe


def test_csv_safe_neutralizes_formula_injection():
    assert csv_safe('=SUM(A1:A10)').startswith("'")
    assert csv_safe('+CMD').startswith("'")
    assert csv_safe('-1+1').startswith("'")
    assert csv_safe('@import').startswith("'")
    assert csv_safe('Normal text') == 'Normal text'
    assert csv_safe(None) == ''


def test_officer_filter_matches_by_id_not_name(client, login_as, make_user, make_officer, make_appointment):
    """Regression test: the officer filter dropdown submits the officer's ID,
    but the backend used to compare against Officer.name, so this filter
    silently returned zero results for every real user clicking it."""
    admin = make_user(role='admin')
    off_a = make_officer(name='Officer Alpha')
    off_b = make_officer(name='Officer Beta')
    student = make_user(role='student')
    make_appointment(student, off_a, date.today(), student_id_num='UNIQUE_A')
    make_appointment(student, off_b, date.today(), student_id_num='UNIQUE_B')
    login_as(admin)

    r = client.get(f'/admin/appointments?officer={off_a.id}')
    assert b'UNIQUE_A' in r.data
    assert b'UNIQUE_B' not in r.data


def test_search_matches_name_id_and_email(client, login_as, make_user, make_officer, make_appointment):
    admin = make_user(role='admin')
    officer = make_officer()
    s1 = make_user(role='student', name='Ahmed Rahman', email='ahmed@iut-dhaka.edu')
    s2 = make_user(role='student', name='Karim Hasan', email='karim@iut-dhaka.edu')
    make_appointment(s1, officer, date.today(), student_id_num='190041001')
    make_appointment(s2, officer, date.today(), student_id_num='190041002')
    login_as(admin)

    r = client.get('/admin/appointments?search=Ahmed')
    assert b'Ahmed Rahman' in r.data and b'Karim Hasan' not in r.data

    r = client.get('/admin/appointments?search=041002')
    assert b'Karim Hasan' in r.data and b'Ahmed Rahman' not in r.data

    r = client.get('/admin/appointments?search=karim@iut')
    assert b'Karim Hasan' in r.data


def test_csv_export_date_range_scoping(client, login_as, make_user, make_officer, make_appointment):
    admin = make_user(role='admin')
    officer = make_officer()
    student = make_user(role='student')
    today = date.today()
    make_appointment(student, officer, today, student_id_num='IN_RANGE')
    make_appointment(student, officer, today + timedelta(days=30), student_id_num='OUT_OF_RANGE')
    login_as(admin)

    r = client.get(f'/admin/export/csv?start_date={today.isoformat()}&end_date={(today+timedelta(days=5)).isoformat()}')
    body = r.data.decode()
    assert 'IN_RANGE' in body
    assert 'OUT_OF_RANGE' not in body


def test_csv_export_with_no_range_includes_everything(client, login_as, make_user, make_officer, make_appointment):
    admin = make_user(role='admin')
    officer = make_officer()
    student = make_user(role='student')
    make_appointment(student, officer, date.today(), student_id_num='A')
    make_appointment(student, officer, date.today() + timedelta(days=90), student_id_num='B')
    login_as(admin)

    r = client.get('/admin/export/csv')
    body = r.data.decode()
    assert 'A' in body and 'B' in body


def test_appointments_list_paginates(client, login_as, make_user, make_officer, make_appointment):
    admin = make_user(role='admin')
    officer = make_officer()
    student = make_user(role='student')
    for i in range(30):
        make_appointment(student, officer, date.today() + timedelta(days=i), student_id_num=f'S{i}')
    login_as(admin)

    r1 = client.get('/admin/appointments')
    assert b'Showing 1' in r1.data

    r2 = client.get('/admin/appointments?page=2')
    assert b'Showing 26' in r2.data


def test_non_admin_cannot_access_appointments_list(client, login_as, make_user):
    student = make_user(role='student')
    login_as(student)
    r = client.get('/admin/appointments', follow_redirects=True)
    assert r.status_code in (200, 403)
    assert b'Manage all appointment bookings' not in r.data
