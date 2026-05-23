"""
Appointment Service for IUT Appointment System
Handles appointment booking, conflict detection, queue management, and priority system
"""

from models import db, Appointment, Officer, OfficerUnavailability, AppointmentTimeline, OfficerWorkingHours
from datetime import datetime, date, timedelta, timezone
import qrcode
from io import BytesIO
import base64

class AppointmentService:
    """Service for managing appointments"""

    @staticmethod
    def check_appointment_conflict(officer_id, appointment_date, appointment_time):
        """
        Check if there's a conflict with existing appointments
        
        Args:
            officer_id (int): ID of the officer
            appointment_date (date): Date of the appointment
            appointment_time (str): Time of the appointment (HH:MM format)
        
        Returns:
            tuple: (bool, str) - (has_conflict, message)
        """
        # Check for existing appointments at the same time
        existing_appointment = Appointment.query.filter_by(
            officer_id=officer_id,
            date=appointment_date,
            time=appointment_time,
            status='Approved'
        ).first()
        
        if existing_appointment:
            return True, "This time slot is already booked"
        
        # Check if officer is unavailable on this date
        unavailability = OfficerUnavailability.query.filter(
            OfficerUnavailability.officer_id == officer_id,
            OfficerUnavailability.start_date <= appointment_date,
            OfficerUnavailability.end_date >= appointment_date
        ).first()
        
        if unavailability:
            return True, f"Officer is unavailable on this date: {unavailability.reason}"
        
        return False, "No conflicts"

    @staticmethod
    def check_office_hours(officer_id, appointment_date, appointment_time):
        """
        Check if the appointment is within office hours
        
        Args:
            officer_id (int): ID of the officer
            appointment_date (date): Date of the appointment
            appointment_time (str): Time of the appointment (HH:MM format)
        
        Returns:
            tuple: (bool, str) - (is_within_hours, message)
        """
        officer = Officer.query.get(officer_id)
        if not officer:
            return False, "Officer not found"
        
        # Convert time strings to comparable format
        try:
            appt_time = datetime.strptime(appointment_time, "%H:%M").time()
            start_time = datetime.strptime(officer.work_start, "%H:%M").time()
            end_time = datetime.strptime(officer.work_end, "%H:%M").time()
        except ValueError:
            return False, "Invalid time format"
        
        # Check if appointment time is within office hours
        if not (start_time <= appt_time < end_time):
            return False, f"Appointment must be between {officer.work_start} and {officer.work_end}"
        
        # Check if it's a day off
        weekday = appointment_date.weekday()
        off_days = officer.get_off_days()
        if weekday in off_days:
            return False, "Officer is not available on this day"
        
        return True, "Within office hours"

    @staticmethod
    def check_daily_limit(officer_id, appointment_date):
        """
        Check if the officer has reached their daily appointment limit
        
        Args:
            officer_id (int): ID of the officer
            appointment_date (date): Date of the appointment
        
        Returns:
            tuple: (bool, str) - (can_book, message)
        """
        officer = Officer.query.get(officer_id)
        if not officer or officer.daily_limit == 0:
            return True, "No daily limit"
        
        # Count approved appointments for this officer on this date
        appointment_count = Appointment.query.filter_by(
            officer_id=officer_id,
            date=appointment_date,
            status='Approved'
        ).count()
        
        if appointment_count >= officer.daily_limit:
            return False, f"Officer has reached their daily limit of {officer.daily_limit} appointments"
        
        return True, f"Can book ({appointment_count}/{officer.daily_limit})"

    @staticmethod
    def generate_queue_number(officer_id, appointment_date, priority='Normal'):
        """
        Generate a queue number for an appointment
        
        Args:
            officer_id (int): ID of the officer
            appointment_date (date): Date of the appointment
            priority (str): Priority level of the appointment
        
        Returns:
            int: Queue number
        """
        # Get all appointments for this officer on this date
        appointments = Appointment.query.filter_by(
            officer_id=officer_id,
            date=appointment_date
        ).all()
        
        # Count by priority
        emergency_count = sum(1 for a in appointments if a.priority == 'Emergency')
        high_count = sum(1 for a in appointments if a.priority == 'High')
        normal_count = sum(1 for a in appointments if a.priority == 'Normal')
        low_count = sum(1 for a in appointments if a.priority == 'Low')
        
        # Assign queue number based on priority
        if priority == 'Emergency':
            return emergency_count + 1
        elif priority == 'High':
            return emergency_count + high_count + 1
        elif priority == 'Normal':
            return emergency_count + high_count + normal_count + 1
        else:  # Low
            return emergency_count + high_count + normal_count + low_count + 1

    @staticmethod
    def calculate_estimated_wait_time(officer_id, appointment_date, appointment_time):
        """
        Calculate estimated waiting time for an appointment
        
        Args:
            officer_id (int): ID of the officer
            appointment_date (date): Date of the appointment
            appointment_time (str): Time of the appointment (HH:MM format)
        
        Returns:
            int: Estimated waiting time in minutes
        """
        officer = Officer.query.get(officer_id)
        if not officer:
            return 0
        
        # Get all appointments for this officer on this date before this time
        try:
            appt_time = datetime.strptime(appointment_time, "%H:%M").time()
        except ValueError:
            return 0
        
        earlier_appointments = Appointment.query.filter(
            Appointment.officer_id == officer_id,
            Appointment.date == appointment_date,
            Appointment.time < appointment_time,
            Appointment.status.in_(['Approved', 'In Progress'])
        ).all()
        
        # Calculate total waiting time
        total_wait = len(earlier_appointments) * officer.avg_appointment_duration
        
        return total_wait

    @staticmethod
    def generate_qr_code(appointment):
        """
        Generate a QR code for an appointment
        
        Args:
            appointment (Appointment): The appointment object
        
        Returns:
            str: Base64 encoded QR code image
        """
        # Create QR code data
        qr_data = f"Appointment ID: {appointment.id}\nStudent: {appointment.student_name}\nDate: {appointment.date}\nTime: {appointment.time}\nOfficer: {appointment.officer.name}"
        
        # Generate QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(qr_data)
        qr.make(fit=True)
        
        # Create image
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to base64
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        
        return img_str

    @staticmethod
    def create_appointment_timeline_entry(appointment, status, note=''):
        """
        Create a timeline entry for an appointment status change
        
        Args:
            appointment (Appointment): The appointment object
            status (str): The new status
            note (str): Optional note for the status change
        
        Returns:
            AppointmentTimeline: The created timeline entry
        """
        timeline_entry = AppointmentTimeline(
            appointment_id=appointment.id,
            status=status,
            note=note
        )
        db.session.add(timeline_entry)
        db.session.commit()
        return timeline_entry

    @staticmethod
    def update_appointment_status(appointment, new_status, note=''):
        """
        Update appointment status and create timeline entry
        
        Args:
            appointment (Appointment): The appointment object
            new_status (str): The new status
            note (str): Optional note for the status change
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            appointment.status = new_status
            appointment.status_updated_at = datetime.now(timezone.utc)
            db.session.commit()
            
            # Create timeline entry
            AppointmentService.create_appointment_timeline_entry(appointment, new_status, note)
            
            return True
        except Exception as e:
            print(f"Error updating appointment status: {str(e)}")
            return False

    @staticmethod
    def get_available_slots(officer_id, appointment_date, duration=60):
        """
        Get available time slots for an officer on a specific date.
        Respects off-days, unavailability, and working hour overrides.
        Slots are returned in display format: "09:00 AM - 10:00 AM" (1-hour intervals).

        Args:
            officer_id (int): ID of the officer
            appointment_date (date): Date to check availability
            duration (int): Unused legacy param (slots are always 1-hour)

        Returns:
            list: List of available time slots in "HH:MM AM - HH:MM AM" format
        """
        officer = Officer.query.get(officer_id)
        if not officer:
            return []
        
        # Check if it's a recurring off-day
        weekday = appointment_date.weekday()
        off_days = officer.get_off_days()
        if weekday in off_days:
            return []  # Officer is off on this day
        
        # Check if officer is unavailable on this date
        unavail = OfficerUnavailability.query.filter(
            OfficerUnavailability.officer_id == officer_id,
            OfficerUnavailability.start_date <= appointment_date,
            OfficerUnavailability.end_date >= appointment_date
        ).first()
        if unavail:
            return []  # Officer is unavailable
        
        # Check for per-weekday working hours override
        override = next((wh for wh in officer.working_hours if wh.weekday == weekday), None)
        if override:
            try:
                start_time = datetime.strptime(override.start_time, "%H:%M").time()
                end_time = datetime.strptime(override.end_time, "%H:%M").time()
            except ValueError:
                return []
        else:
            # Use default office hours
            try:
                start_time = datetime.strptime(officer.work_start, "%H:%M").time()
                end_time = datetime.strptime(officer.work_end, "%H:%M").time()
            except ValueError:
                return []
        
        # Generate all possible slots in display format "HH:MM AM - HH:MM AM"
        # (1-hour intervals to match generate_time_slots in app.py)
        all_slots = []
        current = datetime.combine(appointment_date, start_time)
        end = datetime.combine(appointment_date, end_time)

        while current < end:
            nxt = current + timedelta(hours=1)
            slot_label = f"{current.strftime('%I:%M %p')} - {nxt.strftime('%I:%M %p')}"
            all_slots.append(slot_label)
            current = nxt

        # Get booked slots (both Pending and Approved to prevent double-booking)
        booked_appointments = Appointment.query.filter_by(
            officer_id=officer_id,
            date=appointment_date
        ).filter(Appointment.status.in_(['Approved', 'Pending'])).all()

        booked_slots = [appt.time for appt in booked_appointments]

        # Return available slots (those not already booked)
        available_slots = [slot for slot in all_slots if slot not in booked_slots]

        return available_slots

    @staticmethod
    def suggest_alternative_slots(officer_id, appointment_date, num_suggestions=3):
        """
        Suggest alternative time slots if preferred slot is not available
        
        Args:
            officer_id (int): ID of the officer
            appointment_date (date): Original appointment date
            num_suggestions (int): Number of suggestions to provide
        
        Returns:
            list: List of suggested dates and available slots
        """
        suggestions = []
        
        # Check next 7 days
        for i in range(1, 8):
            check_date = appointment_date + timedelta(days=i)
            available_slots = AppointmentService.get_available_slots(officer_id, check_date)
            
            if available_slots:
                suggestions.append({
                    'date': check_date,
                    'slots': available_slots[:3]  # Limit to 3 slots per date
                })
                
                if len(suggestions) >= num_suggestions:
                    break
        
        return suggestions

    @staticmethod
    def recommend_officer(issue, available_officers):
        """
        Recommend an officer based on their expertise
        
        Args:
            issue (str): The issue/topic for the appointment
            available_officers (list): List of available officers
        
        Returns:
            Officer: Recommended officer or None
        """
        best_match = None
        best_score = 0
        
        for officer in available_officers:
            handles = officer.get_handles()
            
            # Simple matching based on keywords
            score = 0
            for handle in handles:
                if handle.lower() in issue.lower():
                    score += 1
            
            if score > best_score:
                best_score = score
                best_match = officer
        
        return best_match if best_match else (available_officers[0] if available_officers else None)
