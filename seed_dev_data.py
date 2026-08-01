"""
DEV-ONLY DATA SEEDER — NOT A TEST SUITE.

This script calls db.drop_all() and wipes every table before reseeding sample
data. It used to be named test_app.py, which made it easy to run by mistake
against a real database. Running this against production would delete every
real student, officer, and appointment record with no way to undo it.

Safety checks below refuse to run unless ALL of the following are true:
  1. FLASK_ENV=development is set
  2. DATABASE_URL is NOT set (i.e. you're on local SQLite, not the
     production Postgres database)
  3. You type the confirmation phrase when prompted

Usage (local machine only):
    FLASK_ENV=development python seed_dev_data.py
"""
import os
import sys


def _refuse(reason: str):
    print(f"❌ Refusing to run: {reason}")
    print("This script drops and recreates every table. It is for local development only.")
    sys.exit(1)


def _safety_checks():
    if os.environ.get('FLASK_ENV') != 'development':
        _refuse("FLASK_ENV is not 'development'. Set FLASK_ENV=development to run this locally.")

    if os.environ.get('DATABASE_URL'):
        _refuse("DATABASE_URL is set, which means this could be pointing at a real "
                "(e.g. Render/production) database. Unset it to use local SQLite instead.")

    print("⚠️  This will PERMANENTLY DELETE all data in your local database and replace")
    print("    it with sample test data. This cannot be undone.")
    answer = input("Type 'yes, wipe my local database' to continue: ").strip()
    if answer != 'yes, wipe my local database':
        _refuse("confirmation phrase did not match.")


def setup_test_data():
    from app import app, db, bcrypt
    from models import User, Appointment, Officer, Notification
    from datetime import datetime, timedelta, timezone

    with app.app_context():
        # Clear existing data
        db.drop_all()
        db.create_all()

        # Create Officers
        officers_data = [
            ('VC', 'Vice Chancellor'),
            ('Pro VC', 'Pro Vice Chancellor'),
            ('Registrar', 'Registrar'),
            ('Dean', 'Dean of Engineering'),
            ('Finance Officer', 'Chief Finance Officer'),
            ('Student Affairs', 'Director of Student Affairs')
        ]
        officers = []
        for name, desig in officers_data:
            o = Officer(name=name, designation=desig)
            db.session.add(o)
            officers.append(o)
        db.session.commit()

        # Create Admin
        admin_pass = bcrypt.generate_password_hash('admin123').decode('utf-8')
        admin = User(name='System Admin', email='admin@iut-dhaka.edu', password=admin_pass,
                     role='admin', email_verified=True)

        # Create Student
        student_pass = bcrypt.generate_password_hash('student123').decode('utf-8')
        student = User(name='John Doe', email='abdinadiif@iut-dhaka.edu', password=student_pass,
                        role='student', email_verified=True)

        db.session.add(admin)
        db.session.add(student)
        db.session.commit()

        # Create some sample appointments
        today = datetime.now(timezone.utc).date()

        # Find a Monday-Thursday date
        current = today
        while current.strftime('%A') in ['Friday', 'Saturday', 'Sunday']:
            current += timedelta(days=1)

        apt1 = Appointment(
            user_id=student.id,
            student_name='John Doe',
            student_id_num='STU001',
            department='Computer Science',
            officer_id=officers[0].id,
            day=current.strftime('%A'),
            date=current,
            time='09:00 AM - 10:00 AM',
            issue='Discuss research project',
            status='Approved'
        )

        apt2 = Appointment(
            user_id=student.id,
            student_name='John Doe',
            student_id_num='STU001',
            department='Computer Science',
            officer_id=officers[2].id,
            day=current.strftime('%A'),
            date=current,
            time='11:00 AM - 12:00 PM',
            issue='Transcript request',
            status='Pending'
        )

        db.session.add(apt1)
        db.session.add(apt2)

        # Add a notification
        notif = Notification(user_id=student.id, message="Welcome to IUT APPOINTMENT system!")
        db.session.add(notif)

        db.session.commit()

        print("Test data created successfully!")
        print(f"Admin: admin@iut-dhaka.edu / admin123")
        print(f"Student: abdinadiif@iut-dhaka.edu / student123")


if __name__ == '__main__':
    _safety_checks()
    setup_test_data()
