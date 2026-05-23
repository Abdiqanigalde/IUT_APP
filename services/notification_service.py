"""
Notification Service for IUT Appointment System
Handles email notifications, SMS, and WhatsApp integration
"""

from flask_mail import Mail, Message
from datetime import datetime
from models import db, NotificationLog, Appointment, User
import os

mail = Mail()

class NotificationService:
    """Service for managing all types of notifications"""

    @staticmethod
    def send_email(recipient_email, subject, body, html_body=None):
        """
        Send an email notification
        
        Args:
            recipient_email (str): Email address of the recipient
            subject (str): Email subject
            body (str): Plain text email body
            html_body (str): HTML email body (optional)
        
        Returns:
            bool: True if email was sent successfully, False otherwise
        """
        try:
            msg = Message(
                subject=subject,
                recipients=[recipient_email],
                body=body,
                html=html_body
            )
            mail.send(msg)
            return True
        except Exception as e:
            print(f"Error sending email: {str(e)}")
            return False

    @staticmethod
    def log_notification(user_id, notification_type, subject, message, status='pending'):
        """
        Log a notification to the database
        
        Args:
            user_id (int): ID of the user receiving the notification
            notification_type (str): Type of notification (email, sms, whatsapp)
            subject (str): Subject of the notification
            message (str): Content of the notification
            status (str): Status of the notification (pending, sent, failed)
        
        Returns:
            NotificationLog: The created notification log entry
        """
        notification = NotificationLog(
            user_id=user_id,
            type=notification_type,
            subject=subject,
            message=message,
            status=status
        )
        db.session.add(notification)
        db.session.commit()
        return notification

    @staticmethod
    def send_appointment_confirmation(appointment):
        """
        Send appointment confirmation email to student
        
        Args:
            appointment (Appointment): The appointment object
        """
        user = User.query.get(appointment.user_id)
        if not user:
            return False

        subject = f"Appointment Confirmation - {appointment.date} at {appointment.time}"
        
        body = f"""
Dear {user.name},

Your appointment has been confirmed.

Appointment Details:
- Date: {appointment.date}
- Time: {appointment.time}
- Officer: {appointment.officer.name}
- Issue: {appointment.issue}
- Status: {appointment.status}

Please keep this confirmation for your records.

Best regards,
IUT Appointment Management System
"""

        html_body = f"""
<html>
<body>
<h2>Appointment Confirmation</h2>
<p>Dear {user.name},</p>
<p>Your appointment has been confirmed.</p>
<h3>Appointment Details:</h3>
<ul>
<li><strong>Date:</strong> {appointment.date}</li>
<li><strong>Time:</strong> {appointment.time}</li>
<li><strong>Officer:</strong> {appointment.officer.name}</li>
<li><strong>Issue:</strong> {appointment.issue}</li>
<li><strong>Status:</strong> {appointment.status}</li>
</ul>
<p>Please keep this confirmation for your records.</p>
<p>Best regards,<br/>IUT Appointment Management System</p>
</body>
</html>
"""

        if NotificationService.send_email(user.email, subject, body, html_body):
            NotificationService.log_notification(
                user.id, 'email', subject, body, 'sent'
            )
            return True
        else:
            NotificationService.log_notification(
                user.id, 'email', subject, body, 'failed'
            )
            return False

    @staticmethod
    def send_appointment_reminder(appointment):
        """
        Send appointment reminder email to student
        
        Args:
            appointment (Appointment): The appointment object
        """
        user = User.query.get(appointment.user_id)
        if not user or appointment.reminder_sent:
            return False

        subject = f"Reminder: Your Appointment on {appointment.date} at {appointment.time}"
        
        body = f"""
Dear {user.name},

This is a reminder about your upcoming appointment.

Appointment Details:
- Date: {appointment.date}
- Time: {appointment.time}
- Officer: {appointment.officer.name}
- Room: {appointment.officer.room or 'TBD'}

Please arrive 5 minutes early.

Best regards,
IUT Appointment Management System
"""

        html_body = f"""
<html>
<body>
<h2>Appointment Reminder</h2>
<p>Dear {user.name},</p>
<p>This is a reminder about your upcoming appointment.</p>
<h3>Appointment Details:</h3>
<ul>
<li><strong>Date:</strong> {appointment.date}</li>
<li><strong>Time:</strong> {appointment.time}</li>
<li><strong>Officer:</strong> {appointment.officer.name}</li>
<li><strong>Room:</strong> {appointment.officer.room or 'TBD'}</li>
</ul>
<p>Please arrive 5 minutes early.</p>
<p>Best regards,<br/>IUT Appointment Management System</p>
</body>
</html>
"""

        if NotificationService.send_email(user.email, subject, body, html_body):
            NotificationService.log_notification(
                user.id, 'email', subject, body, 'sent'
            )
            appointment.reminder_sent = True
            db.session.commit()
            return True
        else:
            NotificationService.log_notification(
                user.id, 'email', subject, body, 'failed'
            )
            return False

    @staticmethod
    def send_cancellation_notification(appointment, reason=''):
        """
        Send cancellation notification to student
        
        Args:
            appointment (Appointment): The appointment object
            reason (str): Reason for cancellation
        """
        user = User.query.get(appointment.user_id)
        if not user:
            return False

        subject = f"Appointment Cancelled - {appointment.date} at {appointment.time}"
        
        body = f"""
Dear {user.name},

Your appointment has been cancelled.

Appointment Details:
- Date: {appointment.date}
- Time: {appointment.time}
- Officer: {appointment.officer.name}
- Reason: {reason or 'No reason provided'}

You can book a new appointment at any time.

Best regards,
IUT Appointment Management System
"""

        html_body = f"""
<html>
<body>
<h2>Appointment Cancelled</h2>
<p>Dear {user.name},</p>
<p>Your appointment has been cancelled.</p>
<h3>Appointment Details:</h3>
<ul>
<li><strong>Date:</strong> {appointment.date}</li>
<li><strong>Time:</strong> {appointment.time}</li>
<li><strong>Officer:</strong> {appointment.officer.name}</li>
<li><strong>Reason:</strong> {reason or 'No reason provided'}</li>
</ul>
<p>You can book a new appointment at any time.</p>
<p>Best regards,<br/>IUT Appointment Management System</p>
</body>
</html>
"""

        if NotificationService.send_email(user.email, subject, body, html_body):
            NotificationService.log_notification(
                user.id, 'email', subject, body, 'sent'
            )
            return True
        else:
            NotificationService.log_notification(
                user.id, 'email', subject, body, 'failed'
            )
            return False

    @staticmethod
    def send_reschedule_notification(appointment, old_date, old_time):
        """
        Send reschedule notification to student
        
        Args:
            appointment (Appointment): The appointment object
            old_date (str): Previous appointment date
            old_time (str): Previous appointment time
        """
        user = User.query.get(appointment.user_id)
        if not user:
            return False

        subject = f"Appointment Rescheduled - New Date: {appointment.date} at {appointment.time}"
        
        body = f"""
Dear {user.name},

Your appointment has been rescheduled.

Previous Appointment:
- Date: {old_date}
- Time: {old_time}

New Appointment:
- Date: {appointment.date}
- Time: {appointment.time}
- Officer: {appointment.officer.name}

Please update your calendar accordingly.

Best regards,
IUT Appointment Management System
"""

        html_body = f"""
<html>
<body>
<h2>Appointment Rescheduled</h2>
<p>Dear {user.name},</p>
<p>Your appointment has been rescheduled.</p>
<h3>Previous Appointment:</h3>
<ul>
<li><strong>Date:</strong> {old_date}</li>
<li><strong>Time:</strong> {old_time}</li>
</ul>
<h3>New Appointment:</h3>
<ul>
<li><strong>Date:</strong> {appointment.date}</li>
<li><strong>Time:</strong> {appointment.time}</li>
<li><strong>Officer:</strong> {appointment.officer.name}</li>
</ul>
<p>Please update your calendar accordingly.</p>
<p>Best regards,<br/>IUT Appointment Management System</p>
</body>
</html>
"""

        if NotificationService.send_email(user.email, subject, body, html_body):
            NotificationService.log_notification(
                user.id, 'email', subject, body, 'sent'
            )
            return True
        else:
            NotificationService.log_notification(
                user.id, 'email', subject, body, 'failed'
            )
            return False

    @staticmethod
    def send_sms_placeholder(phone_number, message):
        """
        Placeholder for SMS integration
        
        Args:
            phone_number (str): Phone number to send SMS to
            message (str): SMS message content
        
        Returns:
            bool: Always returns True for placeholder
        """
        # This is a placeholder for SMS integration
        # In production, integrate with services like Twilio, AWS SNS, etc.
        print(f"[SMS Placeholder] Sending SMS to {phone_number}: {message}")
        return True

    @staticmethod
    def send_whatsapp_placeholder(phone_number, message):
        """
        Placeholder for WhatsApp integration
        
        Args:
            phone_number (str): Phone number to send WhatsApp message to
            message (str): WhatsApp message content
        
        Returns:
            bool: Always returns True for placeholder
        """
        # This is a placeholder for WhatsApp integration
        # In production, integrate with services like Twilio, Meta WhatsApp Business API, etc.
        print(f"[WhatsApp Placeholder] Sending WhatsApp to {phone_number}: {message}")
        return True
