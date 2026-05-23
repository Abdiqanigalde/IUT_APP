from app import app, db, bcrypt
from models import User, Appointment, Officer, Notification
from datetime import datetime, timedelta, timezone

def setup_test_data():
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
        admin = User(name='System Admin', email='admin@iut-dhaka.edu', password=admin_pass, role='admin')
        
        # Create Student
        student_pass = bcrypt.generate_password_hash('student123').decode('utf-8')
        student = User(name='John Doe', email='abdinadiif@iut-dhaka.edu', password=student_pass, role='student')
        
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
    setup_test_data()
