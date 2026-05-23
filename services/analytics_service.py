"""
Analytics Service for IUT Appointment System
Handles analytics, statistics, and reporting
"""

from models import db, Appointment, Officer, User, Feedback
from datetime import datetime, date, timedelta, timezone
from sqlalchemy import func

class AnalyticsService:
    """Service for analytics and reporting"""

    @staticmethod
    def get_total_appointments(start_date=None, end_date=None):
        """
        Get total number of appointments
        
        Args:
            start_date (date): Start date for filtering
            end_date (date): End date for filtering
        
        Returns:
            int: Total number of appointments
        """
        query = Appointment.query
        
        if start_date:
            query = query.filter(Appointment.date >= start_date)
        if end_date:
            query = query.filter(Appointment.date <= end_date)
        
        return query.count()

    @staticmethod
    def get_completed_appointments(start_date=None, end_date=None):
        """
        Get number of completed appointments
        
        Args:
            start_date (date): Start date for filtering
            end_date (date): End date for filtering
        
        Returns:
            int: Number of completed appointments
        """
        query = Appointment.query.filter_by(status='Completed')
        
        if start_date:
            query = query.filter(Appointment.date >= start_date)
        if end_date:
            query = query.filter(Appointment.date <= end_date)
        
        return query.count()

    @staticmethod
    def get_cancelled_appointments(start_date=None, end_date=None):
        """
        Get number of cancelled appointments
        
        Args:
            start_date (date): Start date for filtering
            end_date (date): End date for filtering
        
        Returns:
            int: Number of cancelled appointments
        """
        query = Appointment.query.filter_by(status='Cancelled')
        
        if start_date:
            query = query.filter(Appointment.date >= start_date)
        if end_date:
            query = query.filter(Appointment.date <= end_date)
        
        return query.count()

    @staticmethod
    def get_cancellation_rate(start_date=None, end_date=None):
        """
        Get cancellation rate as a percentage
        
        Args:
            start_date (date): Start date for filtering
            end_date (date): End date for filtering
        
        Returns:
            float: Cancellation rate as a percentage
        """
        total = AnalyticsService.get_total_appointments(start_date, end_date)
        if total == 0:
            return 0
        
        cancelled = AnalyticsService.get_cancelled_appointments(start_date, end_date)
        return (cancelled / total) * 100

    @staticmethod
    def get_busiest_officers(limit=5, start_date=None, end_date=None):
        """
        Get the busiest officers by appointment count
        
        Args:
            limit (int): Number of officers to return
            start_date (date): Start date for filtering
            end_date (date): End date for filtering
        
        Returns:
            list: List of tuples (officer, appointment_count)
        """
        query = db.session.query(
            Officer,
            func.count(Appointment.id).label('appointment_count')
        ).join(Appointment).group_by(Officer.id)
        
        if start_date:
            query = query.filter(Appointment.date >= start_date)
        if end_date:
            query = query.filter(Appointment.date <= end_date)
        
        query = query.order_by(func.count(Appointment.id).desc()).limit(limit)
        
        return query.all()

    @staticmethod
    def get_peak_booking_hours(start_date=None, end_date=None):
        """
        Get peak booking hours
        
        Args:
            start_date (date): Start date for filtering
            end_date (date): End date for filtering
        
        Returns:
            dict: Dictionary with hour as key and appointment count as value
        """
        query = db.session.query(
            Appointment.time,
            func.count(Appointment.id).label('count')
        ).group_by(Appointment.time)
        
        if start_date:
            query = query.filter(Appointment.date >= start_date)
        if end_date:
            query = query.filter(Appointment.date <= end_date)
        
        query = query.order_by(func.count(Appointment.id).desc())
        
        result = {}
        for time, count in query.all():
            result[time] = count
        
        return result

    @staticmethod
    def get_monthly_trends(year=None, month=None):
        """
        Get monthly appointment trends
        
        Args:
            year (int): Year to filter (optional)
            month (int): Month to filter (optional)
        
        Returns:
            dict: Dictionary with date as key and appointment count as value
        """
        query = db.session.query(
            Appointment.date,
            func.count(Appointment.id).label('count')
        ).group_by(Appointment.date)
        
        if year:
            query = query.filter(db.extract('year', Appointment.date) == year)
        if month:
            query = query.filter(db.extract('month', Appointment.date) == month)
        
        query = query.order_by(Appointment.date)
        
        result = {}
        for date, count in query.all():
            result[str(date)] = count
        
        return result

    @staticmethod
    def get_officer_average_rating(officer_id):
        """
        Get average rating for an officer
        
        Args:
            officer_id (int): ID of the officer
        
        Returns:
            float: Average rating (0-5)
        """
        result = db.session.query(
            func.avg(Feedback.rating).label('avg_rating')
        ).filter(Feedback.officer_id == officer_id).first()
        
        return result.avg_rating if result.avg_rating else 0

    @staticmethod
    def get_officer_feedback_count(officer_id):
        """
        Get number of feedback entries for an officer
        
        Args:
            officer_id (int): ID of the officer
        
        Returns:
            int: Number of feedback entries
        """
        return Feedback.query.filter_by(officer_id=officer_id).count()

    @staticmethod
    def get_appointment_status_distribution(start_date=None, end_date=None):
        """
        Get distribution of appointments by status
        
        Args:
            start_date (date): Start date for filtering
            end_date (date): End date for filtering
        
        Returns:
            dict: Dictionary with status as key and count as value
        """
        query = db.session.query(
            Appointment.status,
            func.count(Appointment.id).label('count')
        ).group_by(Appointment.status)
        
        if start_date:
            query = query.filter(Appointment.date >= start_date)
        if end_date:
            query = query.filter(Appointment.date <= end_date)
        
        result = {}
        for status, count in query.all():
            result[status] = count
        
        return result

    @staticmethod
    def get_appointment_priority_distribution(start_date=None, end_date=None):
        """
        Get distribution of appointments by priority
        
        Args:
            start_date (date): Start date for filtering
            end_date (date): End date for filtering
        
        Returns:
            dict: Dictionary with priority as key and count as value
        """
        query = db.session.query(
            Appointment.priority,
            func.count(Appointment.id).label('count')
        ).group_by(Appointment.priority)
        
        if start_date:
            query = query.filter(Appointment.date >= start_date)
        if end_date:
            query = query.filter(Appointment.date <= end_date)
        
        result = {}
        for priority, count in query.all():
            result[priority] = count
        
        return result

    @staticmethod
    def get_dashboard_summary(start_date=None, end_date=None):
        """
        Get a summary of key metrics for the dashboard
        
        Args:
            start_date (date): Start date for filtering
            end_date (date): End date for filtering
        
        Returns:
            dict: Dictionary with various metrics
        """
        return {
            'total_appointments': AnalyticsService.get_total_appointments(start_date, end_date),
            'completed_appointments': AnalyticsService.get_completed_appointments(start_date, end_date),
            'cancelled_appointments': AnalyticsService.get_cancelled_appointments(start_date, end_date),
            'cancellation_rate': round(AnalyticsService.get_cancellation_rate(start_date, end_date), 2),
            'total_officers': Officer.query.filter_by(is_active=True).count(),
            'total_students': User.query.filter_by(role='student', is_active=True).count(),
            'busiest_officers': AnalyticsService.get_busiest_officers(5, start_date, end_date),
            'peak_hours': AnalyticsService.get_peak_booking_hours(start_date, end_date),
            'status_distribution': AnalyticsService.get_appointment_status_distribution(start_date, end_date),
            'priority_distribution': AnalyticsService.get_appointment_priority_distribution(start_date, end_date),
        }

    @staticmethod
    def get_student_statistics(student_id):
        """
        Get statistics for a specific student
        
        Args:
            student_id (int): ID of the student
        
        Returns:
            dict: Dictionary with student statistics
        """
        total = Appointment.query.filter_by(user_id=student_id).count()
        completed = Appointment.query.filter_by(user_id=student_id, status='Completed').count()
        cancelled = Appointment.query.filter_by(user_id=student_id, status='Cancelled').count()
        pending = Appointment.query.filter_by(user_id=student_id, status='Pending').count()
        
        return {
            'total_appointments': total,
            'completed_appointments': completed,
            'cancelled_appointments': cancelled,
            'pending_appointments': pending,
        }

    @staticmethod
    def export_analytics_report(start_date=None, end_date=None):
        """
        Export analytics report as a dictionary
        
        Args:
            start_date (date): Start date for filtering
            end_date (date): End date for filtering
        
        Returns:
            dict: Complete analytics report
        """
        return {
            'report_date': datetime.now(timezone.utc).isoformat(),
            'period': {
                'start_date': str(start_date) if start_date else 'All time',
                'end_date': str(end_date) if end_date else 'All time',
            },
            'summary': AnalyticsService.get_dashboard_summary(start_date, end_date),
            'monthly_trends': AnalyticsService.get_monthly_trends(),
        }
