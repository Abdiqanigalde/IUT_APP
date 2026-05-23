"""
AI Suggestions Service for IUT Appointment System
Provides smart suggestions for appointments and officer recommendations
"""

from models import db, Officer, Appointment, User
from datetime import datetime, timedelta
from services.appointment_service import AppointmentService

class AISuggestionsService:
    """Service for providing AI-powered suggestions"""

    @staticmethod
    def suggest_available_slots(officer_id, preferred_date, num_suggestions=3):
        """
        Suggest available time slots for an officer
        
        Args:
            officer_id (int): ID of the officer
            preferred_date (date): Preferred appointment date
            num_suggestions (int): Number of suggestions to provide
        
        Returns:
            list: List of suggested slots with dates
        """
        suggestions = []
        
        # Check preferred date first
        available_slots = AppointmentService.get_available_slots(officer_id, preferred_date)
        if available_slots:
            suggestions.append({
                'date': str(preferred_date),
                'slots': available_slots[:num_suggestions],
                'priority': 'preferred'
            })
        
        # If not enough slots, suggest alternative dates
        if len(suggestions) < num_suggestions:
            for i in range(1, 14):  # Check next 2 weeks
                check_date = preferred_date + timedelta(days=i)
                available_slots = AppointmentService.get_available_slots(officer_id, check_date)
                
                if available_slots:
                    suggestions.append({
                        'date': str(check_date),
                        'slots': available_slots[:3],
                        'priority': 'alternative'
                    })
                    
                    if len(suggestions) >= num_suggestions:
                        break
        
        return suggestions[:num_suggestions]

    @staticmethod
    def recommend_officers(issue, num_recommendations=3):
        """
        Recommend officers based on their expertise
        
        Args:
            issue (str): The issue/topic for the appointment
            num_recommendations (int): Number of officers to recommend
        
        Returns:
            list: List of recommended officers with match scores
        """
        # Only recommend active officers
        active_officers = Officer.query.filter_by(is_active=True).all()
        if not active_officers:
            return []
        
        recommendations = []
        
        for officer in active_officers:
            score = AISuggestionsService._calculate_officer_match_score(officer, issue)
            
            if score > 0:
                recommendations.append({
                    'officer': officer,
                    'score': score,
                    'reason': AISuggestionsService._get_match_reason(officer, issue)
                })
        
        # Sort by score descending
        recommendations.sort(key=lambda x: x['score'], reverse=True)
        
        return recommendations[:num_recommendations]

    @staticmethod
    def _calculate_officer_match_score(officer, issue):
        """
        Calculate match score between officer and issue
        
        Args:
            officer (Officer): Officer object
            issue (str): Issue description
        
        Returns:
            float: Match score (0-100)
        """
        score = 0
        issue_lower = issue.lower()
        
        # Check if officer handles the issue
        handles = officer.get_handles()
        if handles:
            for handle in handles:
                if handle.lower() in issue_lower:
                    score += 50
                elif any(word in handle.lower() for word in issue_lower.split()):
                    score += 25
        else:
            # If no specific handles, give a small base score
            score += 10
        
        # Check officer's availability (today)
        try:
            available_slots = AppointmentService.get_available_slots(officer.id, datetime.now().date())
            if available_slots:
                score += 20
        except Exception:
            pass  # If availability check fails, just skip this bonus
        
        # Check officer's average rating
        try:
            from services.analytics_service import AnalyticsService
            avg_rating = AnalyticsService.get_officer_average_rating(officer.id)
            score += (avg_rating / 5) * 15
        except Exception:
            pass  # If rating check fails, skip this bonus
        
        # Check workload (less busy officers get higher score)
        today_appointments = Appointment.query.filter_by(
            officer_id=officer.id,
            date=datetime.now().date(),
            status='Approved'
        ).count()
        
        if today_appointments < 5:
            score += 10
        elif today_appointments < 10:
            score += 5
        
        return min(score, 100)

    @staticmethod
    def _get_match_reason(officer, issue):
        """
        Get reason for officer recommendation
        
        Args:
            officer (Officer): Officer object
            issue (str): Issue description
        
        Returns:
            str: Reason for recommendation
        """
        reasons = []
        issue_lower = issue.lower()
        
        # Check expertise
        handles = officer.get_handles()
        for handle in handles:
            if handle.lower() in issue_lower:
                reasons.append(f"Specializes in {handle}")
        
        # Check availability
        try:
            available_slots = AppointmentService.get_available_slots(officer.id, datetime.now().date())
            if available_slots:
                reasons.append(f"Available today")
        except Exception:
            pass
        
        # Check rating
        try:
            from services.analytics_service import AnalyticsService
            avg_rating = AnalyticsService.get_officer_average_rating(officer.id)
            if avg_rating >= 4.5:
                reasons.append(f"Highly rated ({avg_rating:.1f}/5)")
            elif avg_rating >= 4:
                reasons.append(f"Well-rated ({avg_rating:.1f}/5)")
        except Exception:
            pass
        
        return " • ".join(reasons) if reasons else "Available officer"

    @staticmethod
    def suggest_reschedule(appointment_id):
        """
        Suggest alternative times for rescheduling an appointment
        
        Args:
            appointment_id (int): ID of the appointment
        
        Returns:
            dict: Suggested reschedule options
        """
        appointment = Appointment.query.get(appointment_id)
        if not appointment:
            return None
        
        # Get the appointment's current date (not today)
        current_date = appointment.date if appointment.date > datetime.now().date() else datetime.now().date()
        
        # Suggest slots for the same officer
        suggestions = AppointmentService.suggest_alternative_slots(
            appointment.officer_id,
            current_date,
            num_suggestions=3
        )
        
        return {
            'current_appointment': {
                'date': str(appointment.date),
                'time': appointment.time,
                'officer': appointment.officer.name
            },
            'suggestions': suggestions
        }

    @staticmethod
    def predict_appointment_duration(officer_id, issue_type=None):
        """
        Predict appointment duration based on historical data
        
        Args:
            officer_id (int): ID of the officer
            issue_type (str): Type of issue (optional)
        
        Returns:
            int: Predicted duration in minutes
        """
        officer = Officer.query.get(officer_id)
        if not officer:
            return 15  # Default
        
        # Use officer's average appointment duration
        return officer.avg_appointment_duration

    @staticmethod
    def get_smart_suggestions(user_id, issue=None):
        """
        Get comprehensive smart suggestions for a user
        
        Args:
            user_id (int): ID of the user
            issue (str): Issue description (optional)
        
        Returns:
            dict: Comprehensive suggestions
        """
        user = User.query.get(user_id)
        if not user:
            return None
        
        current_date = datetime.now().date()
        
        suggestions = {
            'user': user.name,
            'recommended_officers': [],
            'available_slots': [],
            'best_time': None,
            'estimated_wait': None
        }
        
        # Get recommended officers
        if issue:
            recommended = AISuggestionsService.recommend_officers(issue, num_recommendations=3)
            suggestions['recommended_officers'] = [
                {
                    'id': rec['officer'].id,
                    'name': rec['officer'].name,
                    'designation': rec['officer'].designation,
                    'score': rec['score'],
                    'reason': rec['reason']
                }
                for rec in recommended
            ]
            
            # Get available slots for top recommended officer
            if recommended:
                top_officer = recommended[0]['officer']
                slots = AppointmentService.get_available_slots(top_officer.id, current_date)
                suggestions['available_slots'] = slots[:5]
                
                # Estimate wait time
                if slots:
                    wait_time = AppointmentService.calculate_estimated_wait_time(
                        top_officer.id, current_date, slots[0]
                    )
                    suggestions['estimated_wait'] = wait_time
        
        # Find best time (least busy hour)
        try:
            from services.analytics_service import AnalyticsService
            peak_hours = AnalyticsService.get_peak_booking_hours()
        except Exception:
            peak_hours = None
        if peak_hours and len(peak_hours) > 0:
            # Find least busy hour
            least_busy_hour = min(peak_hours.items(), key=lambda x: x[1])
            suggestions['best_time'] = least_busy_hour[0]
        
        return suggestions
