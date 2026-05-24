"""Shared utilities: email sending via Brevo HTTP API (SMTP-free)."""
import os
import requests
from flask import current_app


def send_email(subject, recipients, html_body):
    """Send email via Brevo HTTP API — works on Render free plan."""
    api_key = os.environ.get('BREVO_API_KEY') or current_app.config.get('BREVO_API_KEY', '')
    sender_email = os.environ.get('MAIL_USERNAME') or current_app.config.get('MAIL_USERNAME', '')

    if not api_key:
        current_app.logger.warning("BREVO_API_KEY not set — skipping email.")
        return

    if not sender_email:
        sender_email = 'noreply@iut-dhaka.edu'

    to_list = [{"email": r} for r in recipients]

    payload = {
        "sender":      {"name": "IUT Appointment System", "email": sender_email},
        "to":          to_list,
        "subject":     subject,
        "htmlContent": html_body,
    }

    headers = {
        "accept":       "application/json",
        "content-type": "application/json",
        "api-key":      api_key,
    }

    try:
        response = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            json=payload,
            headers=headers,
            timeout=10,
        )
        if response.status_code not in (200, 201):
            current_app.logger.error(f"Brevo email failed: {response.status_code} — {response.text}")
        else:
            current_app.logger.info(f"Email sent via Brevo to {recipients}")
    except Exception as e:
        current_app.logger.error(f"Email failed: {e}")


def appointment_status_email(appointment, status):
    status_colors = {'Approved': '#28a745', 'Rejected': '#dc3545', 'Completed': '#007bff'}
    color = status_colors.get(status, '#6c757d')
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;border:1px solid #eee;border-radius:8px;overflow:hidden;">
      <div style="background:{color};padding:20px;text-align:center;">
        <h2 style="color:white;margin:0;">Appointment {status}</h2>
      </div>
      <div style="padding:30px;">
        <p>Dear <strong>{appointment.student_name}</strong>,</p>
        <p>Your appointment has been <strong>{status.lower()}</strong>.</p>
        <table style="width:100%;border-collapse:collapse;margin:20px 0;">
          <tr style="background:#f8f9fa;"><td style="padding:10px;font-weight:bold;">Officer</td><td style="padding:10px;">{appointment.officer.name} ({appointment.officer.designation})</td></tr>
          <tr><td style="padding:10px;font-weight:bold;">Date</td><td style="padding:10px;">{appointment.date.strftime('%A, %d %B %Y')}</td></tr>
          <tr style="background:#f8f9fa;"><td style="padding:10px;font-weight:bold;">Time</td><td style="padding:10px;">{appointment.time}</td></tr>
          <tr><td style="padding:10px;font-weight:bold;">Reason</td><td style="padding:10px;">{appointment.issue}</td></tr>
        </table>
        <p style="color:#666;font-size:0.9em;">IUT Appointment Management System</p>
      </div>
    </div>"""


def waitlist_promoted_email(appointment, user):
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;border:1px solid #eee;border-radius:8px;overflow:hidden;">
      <div style="background:#17a2b8;padding:20px;text-align:center;">
        <h2 style="color:white;margin:0;">Slot Available — Waitlist Promoted</h2>
      </div>
      <div style="padding:30px;">
        <p>Dear <strong>{user.name}</strong>,</p>
        <p>A slot you were waitlisted for has opened up. A new appointment has been booked for you.</p>
        <table style="width:100%;border-collapse:collapse;margin:20px 0;">
          <tr style="background:#f8f9fa;"><td style="padding:10px;font-weight:bold;">Officer</td><td style="padding:10px;">{appointment.officer.name}</td></tr>
          <tr><td style="padding:10px;font-weight:bold;">Date</td><td style="padding:10px;">{appointment.date.strftime('%A, %d %B %Y')}</td></tr>
          <tr style="background:#f8f9fa;"><td style="padding:10px;font-weight:bold;">Time</td><td style="padding:10px;">{appointment.time}</td></tr>
        </table>
        <p style="color:#666;font-size:0.9em;">IUT Appointment Management System</p>
      </div>
    </div>"""


def booking_confirmation_email(appointment, user):
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;border:1px solid #eee;border-radius:8px;overflow:hidden;">
      <div style="background:#0d4f3c;padding:20px;text-align:center;">
        <h2 style="color:white;margin:0;">Appointment Booked</h2>
        <p style="color:rgba(255,255,255,.8);margin:4px 0 0;">Awaiting admin approval</p>
      </div>
      <div style="padding:30px;">
        <p>Dear <strong>{user.name}</strong>,</p>
        <p>Your appointment request has been submitted and is now <strong>pending approval</strong>.</p>
        <table style="width:100%;border-collapse:collapse;margin:20px 0;">
          <tr style="background:#f8f9fa;"><td style="padding:10px;font-weight:bold;">Officer</td><td style="padding:10px;">{appointment.officer.name} ({appointment.officer.designation})</td></tr>
          <tr><td style="padding:10px;font-weight:bold;">Date</td><td style="padding:10px;">{appointment.date.strftime('%A, %d %B %Y')}</td></tr>
          <tr style="background:#f8f9fa;"><td style="padding:10px;font-weight:bold;">Time</td><td style="padding:10px;">{appointment.time}</td></tr>
          <tr><td style="padding:10px;font-weight:bold;">Reason</td><td style="padding:10px;">{appointment.issue}</td></tr>
          <tr style="background:#f8f9fa;"><td style="padding:10px;font-weight:bold;">Reference ID</td><td style="padding:10px;">#{appointment.id}</td></tr>
        </table>
        <p>You will receive another email once your appointment is approved or rejected.</p>
        <p style="color:#666;font-size:.9em;">IUT Appointment Management System</p>
      </div>
    </div>"""


def reminder_email(appointment, user):
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;border:1px solid #eee;border-radius:8px;overflow:hidden;">
      <div style="background:#fd7e14;padding:20px;text-align:center;">
        <h2 style="color:white;margin:0;">⏰ Appointment Reminder</h2>
        <p style="color:rgba(255,255,255,.9);margin:4px 0 0;">Your appointment is tomorrow</p>
      </div>
      <div style="padding:30px;">
        <p>Dear <strong>{user.name}</strong>,</p>
        <p>This is a reminder that you have an approved appointment <strong>tomorrow</strong>.</p>
        <table style="width:100%;border-collapse:collapse;margin:20px 0;">
          <tr style="background:#fff3cd;"><td style="padding:10px;font-weight:bold;">Officer</td><td style="padding:10px;">{appointment.officer.name}</td></tr>
          <tr><td style="padding:10px;font-weight:bold;">Date</td><td style="padding:10px;">{appointment.date.strftime('%A, %d %B %Y')}</td></tr>
          <tr style="background:#fff3cd;"><td style="padding:10px;font-weight:bold;">Time</td><td style="padding:10px;">{appointment.time}</td></tr>
          <tr><td style="padding:10px;font-weight:bold;">Location</td><td style="padding:10px;">{appointment.officer.room or 'Check with the office'}</td></tr>
        </table>
        <p><strong>Please arrive 5 minutes early</strong> and bring your student ID.</p>
        <p style="color:#666;font-size:.9em;">IUT Appointment Management System</p>
      </div>
    </div>"""


def rejection_email(appointment, user, note=''):
    note_row = f'<tr><td style="padding:10px;font-weight:bold;">Reason</td><td style="padding:10px;color:#dc3545;">{note}</td></tr>' if note else ''
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;border:1px solid #eee;border-radius:8px;overflow:hidden;">
      <div style="background:#dc3545;padding:20px;text-align:center;">
        <h2 style="color:white;margin:0;">Appointment Rejected</h2>
      </div>
      <div style="padding:30px;">
        <p>Dear <strong>{user.name}</strong>,</p>
        <p>Unfortunately your appointment request has been <strong>rejected</strong>.</p>
        <table style="width:100%;border-collapse:collapse;margin:20px 0;">
          <tr style="background:#f8f9fa;"><td style="padding:10px;font-weight:bold;">Officer</td><td style="padding:10px;">{appointment.officer.name}</td></tr>
          <tr><td style="padding:10px;font-weight:bold;">Date</td><td style="padding:10px;">{appointment.date.strftime('%A, %d %B %Y')}</td></tr>
          <tr style="background:#f8f9fa;"><td style="padding:10px;font-weight:bold;">Time</td><td style="padding:10px;">{appointment.time}</td></tr>
          {note_row}
        </table>
        <p>You may book a new appointment at a different time.</p>
        <p style="color:#666;font-size:.9em;">IUT Appointment Management System</p>
      </div>
    </div>"""


def email_verification_email(user, verify_url):
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;border:1px solid #eee;border-radius:8px;overflow:hidden;">
      <div style="background:#0d4f3c;padding:24px;text-align:center;">
        <h2 style="color:white;margin:0;">Verify your IUT email</h2>
      </div>
      <div style="padding:30px;">
        <p>Dear <strong>{user.name}</strong>,</p>
        <p>Thank you for registering. Please verify your email address by clicking the button below:</p>
        <div style="text-align:center;margin:30px 0;">
          <a href="{verify_url}" style="background:#0d4f3c;color:white;padding:14px 30px;border-radius:6px;text-decoration:none;font-weight:bold;">Verify Email Address</a>
        </div>
        <p style="color:#666;font-size:.85em;">This link expires in 24 hours. If you did not register, ignore this email.</p>
        <p style="color:#666;font-size:.85em;">IUT Appointment Management System</p>
      </div>
    </div>"""


def password_reset_email(user, reset_url):
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;border:1px solid #eee;border-radius:8px;overflow:hidden;">
      <div style="background:#4361ee;padding:24px;text-align:center;">
        <h2 style="color:white;margin:0;">Password Reset Request</h2>
      </div>
      <div style="padding:30px;">
        <p>Dear <strong>{user.name}</strong>,</p>
        <p>We received a request to reset your password. Click below to set a new password:</p>
        <div style="text-align:center;margin:30px 0;">
          <a href="{reset_url}" style="background:#4361ee;color:white;padding:14px 30px;border-radius:6px;text-decoration:none;font-weight:bold;">Reset Password</a>
        </div>
        <p style="color:#666;font-size:.85em;">This link expires in 1 hour. If you did not request a reset, ignore this email.</p>
        <p style="color:#666;font-size:.85em;">IUT Appointment Management System</p>
      </div>
    </div>"""


def qr_appointment_email(appointment, user, qr_base64):
    qr_info = f"""Appointment ID: {appointment.id}
Student: {user.name}
Officer: {appointment.officer.name}
Date: {appointment.date.strftime('%d %B %Y')}
Time: {appointment.time}
Room: {appointment.officer.room or 'N/A'}
Status: Approved"""

    return f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;border:1px solid #eee;border-radius:8px;overflow:hidden;">
      <div style="background:#0d4f3c;padding:24px;text-align:center;">
        <h2 style="color:white;margin:0;">Your Appointment QR Ticket</h2>
        <p style="color:rgba(255,255,255,.8);margin:4px 0 0;">Appointment #{appointment.id} — Present this at check-in</p>
      </div>
      <div style="padding:30px;text-align:center;">
        <p>Dear <strong>{user.name}</strong>, your appointment has been <strong>Approved</strong>.</p>
        <table style="width:100%;border-collapse:collapse;margin:16px 0;text-align:left;">
          <tr style="background:#f8f9fa;"><td style="padding:10px;font-weight:bold;">Officer</td><td style="padding:10px;">{appointment.officer.name}</td></tr>
          <tr><td style="padding:10px;font-weight:bold;">Date</td><td style="padding:10px;">{appointment.date.strftime('%A, %d %B %Y')}</td></tr>
          <tr style="background:#f8f9fa;"><td style="padding:10px;font-weight:bold;">Time</td><td style="padding:10px;">{appointment.time}</td></tr>
          <tr><td style="padding:10px;font-weight:bold;">Location</td><td style="padding:10px;">{appointment.officer.room or 'Check with office'}</td></tr>
        </table>
        <p style="font-weight:bold;">Show this QR code to the officer for check-in:</p>
        <img src="data:image/png;base64,{qr_base64}" alt="QR Code"
          style="width:180px;height:180px;border:4px solid #0d4f3c;border-radius:8px;margin:12px auto;display:block;">
        <div style="margin-top:20px;background:#f8f9fa;padding:15px;border-radius:8px;text-align:left;">
          <h4 style="margin-top:0;color:#0d4f3c;">QR Information</h4>
          <pre style="white-space:pre-wrap;font-size:14px;color:#333;margin:0;">{qr_info}</pre>
        </div>
        <p style="color:#666;font-size:.85em;margin-top:20px;">Arrive 5 minutes early with your student ID.</p>
        <p style="color:#666;font-size:.85em;">IUT Appointment Management System</p>
      </div>
    </div>"""
