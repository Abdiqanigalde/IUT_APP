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

        # Create Officers (matches the real IUT staff roster in
        # IUT_Officer_Demo_Accounts_Updated.txt so the User accounts below
        # line up with real Officer records for appointment routing)
        officers_data = [
            ('Prof. Dr. Md Mamun Bin Ibne Reaz', 'Vice Chancellor', 'vc@iut-dhaka.edu'),
            ('Dr. Hissein Araby Nour', 'Pro Vice Chancellor', 'provc@iut-dhaka.edu'),
            ('Dr. Mwebesa Umar', 'Registrar', 'registrar@iut-dhaka.edu'),
            ('Engr. Noman Ahmed Khan', 'Deputy Registrar', 'nak@iut-dhaka.edu'),
            ('Abdoul-Azize Alioum', 'Sr. Assistant Registrar', 'abdoulazize@iut-dhaka.edu'),
            ('Mr. Md. Mafizur Rahman', 'Section Officer', 'mafiz@iut-dhaka.edu'),
            ('Mr. Md. Rafiqul Islam', 'Senior Assistant Administrative Officer', 'rafiqul@iut-dhaka.edu'),
            ('Mr. Md. Enamul Hoque', 'Sr. Office Attendant', 'enamul@iut-dhaka.edu'),
        ]
        officers = []
        for name, desig, email in officers_data:
            o = Officer(name=name, designation=desig, email=email, is_active=True)
            db.session.add(o)
            officers.append(o)
        db.session.commit()

        # Create every default account from IUT_Officer_Demo_Accounts_Updated.txt.
        # (Passwords here match that file exactly — keep the two in sync.)
        default_users = [
            ('System Admin', 'admin@iut-dhaka.edu', 'Admin@IUT2026!', 'admin'),
            ('Super Admin', 'superadmin@iut-dhaka.edu', 'SuperAdmin@2026!', 'super_admin'),
            ('Prof. Dr. Md Mamun Bin Ibne Reaz', 'vc@iut-dhaka.edu', 'VC@IUT2026!', 'officer'),
            ('Dr. Hissein Araby Nour', 'provc@iut-dhaka.edu', 'PROVC@IUT2026!', 'officer'),
            ('Visa Officer', 'visaofficer@iut-dhaka.edu', 'visaofficer@2026!', 'visa_officer'),
            ('Student', 'abdinadiif@iut-dhaka.edu', 'Abdmar716', 'student'),
            ('Dr. Mwebesa Umar', 'registrar@iut-dhaka.edu', 'Registrar@IUT2026!', 'officer'),
            ('Engr. Noman Ahmed Khan', 'nak@iut-dhaka.edu', 'DeputyReg@IUT2026!', 'officer'),
            ('Abdoul-Azize Alioum', 'abdoulazize@iut-dhaka.edu', 'SrRegistrar@IUT2026!', 'officer'),
            ('Mr. Md. Mafizur Rahman', 'mafiz@iut-dhaka.edu', 'Section@IUT2026!', 'officer'),
            ('Mr. Md. Rafiqul Islam', 'rafiqul@iut-dhaka.edu', 'AdminOfficer@IUT2026!', 'officer'),
            ('Mr. Md. Enamul Hoque', 'enamul@iut-dhaka.edu', 'Office@IUT2026!', 'officer'),
        ]
        users_by_email = {}
        for name, email, pw, role in default_users:
            hashed = bcrypt.generate_password_hash(pw).decode('utf-8')
            u = User(name=name, email=email, password=hashed, role=role, email_verified=True)
            db.session.add(u)
            users_by_email[email] = u
        db.session.commit()

        admin = users_by_email['admin@iut-dhaka.edu']
        student = users_by_email['abdinadiif@iut-dhaka.edu']

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
        print("Default accounts (see IUT_Officer_Demo_Accounts_Updated.txt):")
        for name, email, pw, role in default_users:
            print(f"  {role:<12} {email} / {pw}")


if __name__ == '__main__':
    _safety_checks()
    setup_test_data()
