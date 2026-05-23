from flask_wtf import FlaskForm
from wtforms import (StringField, PasswordField, SubmitField, SelectField,
                     TextAreaField, DateField, IntegerField, TimeField, BooleanField, SelectMultipleField)
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError, Optional, NumberRange
from models import User

class RegistrationForm(FlaskForm):
    name = StringField('Full Name', validators=[DataRequired(), Length(min=2, max=100)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    # SECURITY: Only 'student' is offered publicly. Admin/Officer created by Super Admin only.
    role = SelectField('Role', choices=[('student', 'Student')], validators=[DataRequired()])
    submit = SubmitField('Sign Up')

    def validate_email(self, email):
        if not email.data.lower().endswith('@iut-dhaka.edu'):
            raise ValidationError('Only @iut-dhaka.edu email addresses are allowed.')
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('That email is already taken.')

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember = BooleanField('Remember Me')
    submit = SubmitField('Login')

class AppointmentForm(FlaskForm):
    student_name = StringField('Full Name', validators=[DataRequired()])
    student_id_num = StringField('Student ID', validators=[DataRequired()])
    department = StringField('Department', validators=[DataRequired()])
    officer = SelectField('Officer', coerce=int, validators=[DataRequired()])
    date = DateField('Date', validators=[DataRequired()])
    time = SelectField('Time Slot', choices=[], validators=[DataRequired()])
    issue = TextAreaField('Appointment Reason', validators=[DataRequired()])
    submit = SubmitField('Book Appointment')

class RescheduleForm(FlaskForm):
    date = DateField('New Date', validators=[DataRequired()])
    time = SelectField('New Time Slot', choices=[], validators=[DataRequired()])
    submit = SubmitField('Reschedule')

class OfficerForm(FlaskForm):
    name = StringField('Officer Name', validators=[DataRequired()])
    designation = StringField('Designation', validators=[DataRequired()])
    work_start = StringField('Work Start (HH:MM)', validators=[DataRequired()], default='08:00')
    work_end = StringField('Work End (HH:MM)', validators=[DataRequired()], default='17:00')
    daily_limit = IntegerField('Max Appointments/Day (0=unlimited)', validators=[NumberRange(min=0)], default=0)
    recurring_off_days = SelectMultipleField('Recurring Off Days',
        choices=[('0','Monday'),('1','Tuesday'),('2','Wednesday'),('3','Thursday'),
                 ('4','Friday'),('5','Saturday'),('6','Sunday')],
        default=['4','5','6'])
    submit = SubmitField('Save Officer')

class WorkingHoursForm(FlaskForm):
    weekday = SelectField('Day', coerce=int,
        choices=[(0,'Monday'),(1,'Tuesday'),(2,'Wednesday'),(3,'Thursday'),(4,'Friday')])
    start_time = StringField('Start (HH:MM)', validators=[DataRequired()], default='08:00')
    end_time = StringField('End (HH:MM)', validators=[DataRequired()], default='17:00')
    submit = SubmitField('Save Hours')

class ProfileForm(FlaskForm):
    name = StringField('Full Name', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()])
    student_id_num = StringField('Student ID', validators=[Optional()])
    department = StringField('Department', validators=[Optional()])
    current_password = PasswordField('Current Password', validators=[Optional()])
    new_password = PasswordField('New Password (min 6 chars)', validators=[Optional(), Length(min=6)])
    confirm_new_password = PasswordField('Confirm New Password',
        validators=[EqualTo('new_password', message='New passwords must match.')])
    submit = SubmitField('Update Profile')

    def validate_email(self, email):
        if not email.data.lower().endswith('@iut-dhaka.edu'):
            raise ValidationError('Only @iut-dhaka.edu email addresses are allowed.')

class ForgotPasswordForm(FlaskForm):
    email = StringField('Email Address', validators=[DataRequired(), Email()])
    submit = SubmitField('Send Reset Link')

class ResetPasswordForm(FlaskForm):
    new_password = PasswordField('New Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm Password',
        validators=[DataRequired(), EqualTo('new_password', message='Passwords must match.')])
    submit = SubmitField('Reset Password')

class UnavailabilityForm(FlaskForm):
    start_date = DateField('From Date', validators=[DataRequired()])
    end_date = DateField('To Date', validators=[DataRequired()])
    reason = StringField('Reason', validators=[DataRequired(), Length(max=255)])
    submit = SubmitField('Mark Unavailable')

class OfficerProfileForm(FlaskForm):
    name = StringField('Officer Name', validators=[DataRequired()])
    designation = StringField('Designation', validators=[DataRequired()])
    bio = TextAreaField('Bio / About', validators=[Optional(), Length(max=500)])
    handles = StringField('Issues Handled (comma-separated)', validators=[Optional(), Length(max=300)])
    email = StringField('Office Email', validators=[Optional(), Email()])
    login_email = StringField('Login Email (for officer portal)', validators=[DataRequired(), Email()])
    login_password = PasswordField('Login Password', validators=[DataRequired(), Length(min=6)])
    photo_url = StringField('Photo Filename (e.g. VC.jpg)', validators=[Optional(), Length(max=255)])
    room = StringField('Room / Office Location', validators=[Optional()])
    work_start = StringField('Work Start (HH:MM)', validators=[DataRequired()], default='08:00')
    work_end = StringField('Work End (HH:MM)', validators=[DataRequired()], default='17:00')
    daily_limit = IntegerField('Max Appointments/Day (0=unlimited)', validators=[NumberRange(min=0)], default=0)
    recurring_off_days = SelectMultipleField('Recurring Off Days',
        choices=[('0','Monday'),('1','Tuesday'),('2','Wednesday'),('3','Thursday'),
                 ('4','Friday'),('5','Saturday'),('6','Sunday')],
        default=['4','5','6'])
    submit = SubmitField('Save Officer')

class RejectNoteForm(FlaskForm):
    rejection_note = TextAreaField('Reason for Rejection', validators=[DataRequired(), Length(max=300)])
    submit = SubmitField('Confirm Rejection')

class BulkActionForm(FlaskForm):
    action = SelectField('Action', choices=[('Approved','Approve Selected'),('Rejected','Reject Selected')])
    submit = SubmitField('Apply')
