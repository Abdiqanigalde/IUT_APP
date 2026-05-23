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
        suggestions = []
        available_slots = AppointmentService.get_available_slots(officer_id, preferred_date)
        if available_slots:
            suggestions.append({
                'date': str(preferred_date),
                'slots': available_slots[:num_suggestions],
                'priority': 'preferred'
            })
        if len(suggestions) < num_suggestions:
            for i in range(1, 14):
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

        recommendations.sort(key=lambda x: x['score'], reverse=True)
        return recommendations[:num_recommendations]

    @staticmethod
    def _calculate_officer_match_score(officer, issue):
        """
        Calculate match score between officer and issue.
        Returns 0 if no keyword match — availability/rating bonuses
        only apply on top of a real keyword match.
        """
        issue_lower = issue.lower()
        issue_words = set(issue_lower.split())

        handles = officer.get_handles()

        # ── Step 1: keyword match (required) ─────────────────────────────────
        keyword_score = 0
        if handles:
            for handle in handles:
                handle_lower = handle.lower().strip()
                handle_words = set(handle_lower.split())

                if handle_lower in issue_lower:
                    # Exact phrase match — strongest signal
                    keyword_score += 60
                elif handle_words & issue_words:
                    # At least one word in common
                    keyword_score += 30
        else:
            # Officer has no defined keywords — can't be meaningfully matched
            return 0

        # No keyword match at all → don't recommend this officer
        if keyword_score == 0:
            return 0

        # Cap keyword score at 70
        keyword_score = min(keyword_score, 70)

        bonus = 0

        # ── Step 2: availability bonus (max +15) ──────────────────────────────
        try:
            available_slots = AppointmentService.get_available_slots(
                officer.id, datetime.now().date()
            )
            if available_slots:
                bonus += 15
        except Exception:
            pass

        # ── Step 3: rating bonus (max +10) ───────────────────────────────────
        try:
            from services.analytics_service import AnalyticsService
            avg_rating = AnalyticsService.get_officer_average_rating(officer.id)
            bonus += (avg_rating / 5) * 10
        except Exception:
            pass

        # ── Step 4: workload bonus (max +5) ──────────────────────────────────
        try:
            today_appointments = Appointment.query.filter_by(
                officer_id=officer.id,
                date=datetime.now().date(),
                status='Approved'
            ).count()
            if today_appointments < 5:
                bonus += 5
            elif today_appointments < 10:
                bonus += 2
        except Exception:
            pass

        return min(round(keyword_score + bonus), 100)

    @staticmethod
    def _get_match_reason(officer, issue):
        reasons = []
        issue_lower = issue.lower()
        issue_words = set(issue_lower.split())

        handles = officer.get_handles()
        for handle in handles:
            handle_lower = handle.lower().strip()
            handle_words = set(handle_lower.split())
            if handle_lower in issue_lower or handle_words & issue_words:
                reasons.append(f"Specializes in {handle}")

        try:
            available_slots = AppointmentService.get_available_slots(
                officer.id, datetime.now().date()
            )
            if available_slots:
                reasons.append("Available today")
        except Exception:
            pass

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
        appointment = Appointment.query.get(appointment_id)
        if not appointment:
            return None

        current_date = (
            appointment.date
            if appointment.date > datetime.now().date()
            else datetime.now().date()
        )

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
        officer = Officer.query.get(officer_id)
        if not officer:
            return 15
        return officer.avg_appointment_duration

    @staticmethod
    def get_smart_suggestions(user_id, issue=None):
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

            if recommended:
                top_officer = recommended[0]['officer']
                slots = AppointmentService.get_available_slots(top_officer.id, current_date)
                suggestions['available_slots'] = slots[:5]

                if slots:
                    wait_time = AppointmentService.calculate_estimated_wait_time(
                        top_officer.id, current_date, slots[0]
                    )
                    suggestions['estimated_wait'] = wait_time

        try:
            from services.analytics_service import AnalyticsService
            peak_hours = AnalyticsService.get_peak_booking_hours()
            if peak_hours and len(peak_hours) > 0:
                least_busy_hour = min(peak_hours.items(), key=lambda x: x[1])
                suggestions['best_time'] = least_busy_hour[0]
        except Exception:
            pass

        return suggestions
