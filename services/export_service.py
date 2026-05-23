"""
Export Service for IUT Appointment System
Handles PDF and Excel report generation
"""

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib import colors
from datetime import datetime
import csv
import io
from models import Appointment, Officer, User, Feedback

class ExportService:
    """Service for exporting reports"""

    @staticmethod
    def generate_pdf_report(appointments, title="Appointment Report"):
        """
        Generate a PDF report of appointments
        
        Args:
            appointments (list): List of Appointment objects
            title (str): Title of the report
        
        Returns:
            bytes: PDF file content
        """
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        elements = []
        
        # Styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#1f4788'),
            spaceAfter=30,
            alignment=1  # Center alignment
        )
        
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#1f4788'),
            spaceAfter=12,
        )
        
        # Title
        elements.append(Paragraph(title, title_style))
        elements.append(Paragraph(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))
        elements.append(Spacer(1, 0.3*inch))
        
        # Table data
        table_data = [['ID', 'Student', 'Officer', 'Date', 'Time', 'Status', 'Priority']]
        
        for appointment in appointments:
            table_data.append([
                str(appointment.id),
                appointment.student_name,
                appointment.officer.name,
                str(appointment.date),
                appointment.time,
                appointment.status,
                appointment.priority
            ])
        
        # Create table
        table = Table(table_data, colWidths=[0.6*inch, 1.2*inch, 1.2*inch, 1*inch, 0.8*inch, 1*inch, 0.8*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f0f0')]),
        ]))
        
        elements.append(table)
        elements.append(Spacer(1, 0.3*inch))
        elements.append(Paragraph(f"Total Appointments: {len(appointments)}", styles['Normal']))
        
        # Build PDF
        doc.build(elements)
        buffer.seek(0)
        return buffer.getvalue()

    @staticmethod
    def generate_csv_report(appointments, filename="appointments.csv"):
        """
        Generate a CSV report of appointments
        
        Args:
            appointments (list): List of Appointment objects
            filename (str): Name of the CSV file
        
        Returns:
            bytes: CSV file content
        """
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        
        # Header
        writer.writerow(['ID', 'Student Name', 'Student ID', 'Department', 'Officer', 'Date', 'Time', 'Issue', 'Status', 'Priority', 'Created At'])
        
        # Data
        for appointment in appointments:
            writer.writerow([
                appointment.id,
                appointment.student_name,
                appointment.student_id_num,
                appointment.department,
                appointment.officer.name,
                appointment.date,
                appointment.time,
                appointment.issue,
                appointment.status,
                appointment.priority,
                appointment.created_at.strftime('%Y-%m-%d %H:%M:%S')
            ])
        
        return buffer.getvalue().encode('utf-8')

    @staticmethod
    def generate_monthly_summary_pdf(year, month):
        """
        Generate a monthly summary PDF report
        
        Args:
            year (int): Year
            month (int): Month
        
        Returns:
            bytes: PDF file content
        """
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        elements = []
        
        # Styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#1f4788'),
            spaceAfter=30,
            alignment=1
        )
        
        # Title
        month_name = datetime(year, month, 1).strftime('%B %Y')
        elements.append(Paragraph(f"Monthly Summary - {month_name}", title_style))
        elements.append(Spacer(1, 0.3*inch))
        
        # Get appointments for the month
        from sqlalchemy import func, and_
        appointments = Appointment.query.filter(
            and_(
                func.year(Appointment.date) == year,
                func.month(Appointment.date) == month
            )
        ).all()
        
        # Statistics
        total = len(appointments)
        completed = sum(1 for a in appointments if a.status == 'Completed')
        cancelled = sum(1 for a in appointments if a.status == 'Cancelled')
        pending = sum(1 for a in appointments if a.status == 'Pending')
        
        stats_data = [
            ['Metric', 'Count'],
            ['Total Appointments', str(total)],
            ['Completed', str(completed)],
            ['Cancelled', str(cancelled)],
            ['Pending', str(pending)],
        ]
        
        stats_table = Table(stats_data, colWidths=[3*inch, 2*inch])
        stats_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        
        elements.append(stats_table)
        elements.append(Spacer(1, 0.5*inch))
        
        # Busiest officers
        elements.append(Paragraph("Top Officers by Appointments", styles['Heading2']))
        elements.append(Spacer(1, 0.2*inch))
        
        officer_stats = {}
        for appointment in appointments:
            officer_name = appointment.officer.name
            officer_stats[officer_name] = officer_stats.get(officer_name, 0) + 1
        
        officer_data = [['Officer', 'Appointments']]
        for officer, count in sorted(officer_stats.items(), key=lambda x: x[1], reverse=True)[:5]:
            officer_data.append([officer, str(count)])
        
        officer_table = Table(officer_data, colWidths=[3*inch, 2*inch])
        officer_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        
        elements.append(officer_table)
        
        # Build PDF
        doc.build(elements)
        buffer.seek(0)
        return buffer.getvalue()

    @staticmethod
    def generate_officer_report_pdf(officer_id, start_date=None, end_date=None):
        """
        Generate a report for a specific officer
        
        Args:
            officer_id (int): ID of the officer
            start_date (date): Start date for filtering
            end_date (date): End date for filtering
        
        Returns:
            bytes: PDF file content
        """
        officer = Officer.query.get(officer_id)
        if not officer:
            return None
        
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        elements = []
        
        # Styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#1f4788'),
            spaceAfter=30,
            alignment=1
        )
        
        # Title
        elements.append(Paragraph(f"Officer Report - {officer.name}", title_style))
        elements.append(Paragraph(f"Designation: {officer.designation}", styles['Normal']))
        elements.append(Paragraph(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))
        elements.append(Spacer(1, 0.3*inch))
        
        # Get appointments
        query = Appointment.query.filter_by(officer_id=officer_id)
        if start_date:
            query = query.filter(Appointment.date >= start_date)
        if end_date:
            query = query.filter(Appointment.date <= end_date)
        
        appointments = query.all()
        
        # Statistics
        total = len(appointments)
        completed = sum(1 for a in appointments if a.status == 'Completed')
        cancelled = sum(1 for a in appointments if a.status == 'Cancelled')
        
        # Average rating
        feedbacks = Feedback.query.filter_by(officer_id=officer_id).all()
        avg_rating = sum(f.rating for f in feedbacks) / len(feedbacks) if feedbacks else 0
        
        stats_data = [
            ['Metric', 'Value'],
            ['Total Appointments', str(total)],
            ['Completed', str(completed)],
            ['Cancelled', str(cancelled)],
            ['Average Rating', f"{avg_rating:.2f}/5.0"],
            ['Total Feedback', str(len(feedbacks))],
        ]
        
        stats_table = Table(stats_data, colWidths=[3*inch, 2*inch])
        stats_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        
        elements.append(stats_table)
        
        # Build PDF
        doc.build(elements)
        buffer.seek(0)
        return buffer.getvalue()
