"""
Referred Exam Registration blueprint.

Digitizes the paper-based "referred exam" course registration process:
  1. Student fills in up to 3 courses online and submits.
  2. Md. Enamul Hoque (the officer flagged `handles_referred_exam` on the
     Officer table, under the Office of the Registrar) reviews it, gets the
     required sign-offs done on his end, and marks it "Ready".
  3. The student gets notified (in-app + email) that their paper is ready
     to collect.
"""
from flask import Blueprint, render_template, redirect, url_for, flash, request, Response
from flask_login import login_required, current_user
from models import db, ReferredExamRegistration, Officer, Notification, User
from datetime import datetime, timezone

referred_exam_bp = Blueprint('referred_exam', __name__)

ACTIVE_STATUSES = ('Pending', 'Ready')


def get_referred_exam_officer():
    """The officer currently responsible for processing referred exam
    registrations (flagged by an admin on their officer profile)."""
    return Officer.query.filter_by(handles_referred_exam=True, is_active=True).first()


def get_officer_record_for(user):
    return Officer.query.filter_by(email=user.email).first()


def send_referred_exam_email(student, status, note='', officer=None):
    """Email the student when their referred exam registration status changes."""
    try:
        from utils import send_email

        if status == 'Ready':
            subject = '📄 Your Referred Exam Paper Is Ready — IUT'
            officer_line = f' from <strong>{officer.name}</strong> ({officer.room or "office"})' if officer else ''
            body = f"""
            <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">
              <div style="background:linear-gradient(135deg,#6d28d9,#8b5cf6);padding:32px;border-radius:12px 12px 0 0;text-align:center;">
                <h1 style="color:white;margin:0;font-size:1.6rem;">📄 Your Paper Is Ready!</h1>
              </div>
              <div style="background:#f9fafb;padding:28px;border-radius:0 0 12px 12px;border:1px solid #e5e7eb;">
                <p style="font-size:1rem;color:#374151;">Dear <strong>{student.name}</strong>,</p>
                <p style="color:#374151;">Your referred exam registration has been processed and signed off. Please come collect it{officer_line}.</p>
                {"<div style='background:#f5f3ff;border-left:4px solid #8b5cf6;padding:12px 16px;border-radius:6px;margin:16px 0;'><strong>Note:</strong> " + note + "</div>" if note else ""}
                <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0;">
                <p style="color:#9ca3af;font-size:.82rem;text-align:center;">IUT University Appointment Management System</p>
              </div>
            </div>
            """
        elif status == 'Rejected':
            subject = '❌ Referred Exam Registration Needs Correction — IUT'
            body = f"""
            <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">
              <div style="background:linear-gradient(135deg,#991b1b,#dc2626);padding:32px;border-radius:12px 12px 0 0;text-align:center;">
                <h1 style="color:white;margin:0;font-size:1.6rem;">❌ Registration Rejected</h1>
              </div>
              <div style="background:#f9fafb;padding:28px;border-radius:0 0 12px 12px;border:1px solid #e5e7eb;">
                <p style="font-size:1rem;color:#374151;">Dear <strong>{student.name}</strong>,</p>
                <p style="color:#374151;">Your referred exam registration has been <strong style="color:#dc2626;">rejected</strong>.</p>
                {"<div style='background:#fef2f2;border-left:4px solid #ef4444;padding:12px 16px;border-radius:6px;margin:16px 0;'><strong>Reason:</strong> " + note + "</div>" if note else ""}
                <p style="color:#374151;">Please log in to review the feedback and resubmit.</p>
                <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0;">
                <p style="color:#9ca3af;font-size:.82rem;text-align:center;">IUT University Appointment Management System</p>
              </div>
            </div>
            """
        else:
            return

        send_email(subject, [student.email], body)
        print(f'[IUT] Referred exam email sent to {student.email} — {status}')

    except Exception as e:
        print(f'[IUT] Referred exam email error: {e}')


# ── Student side ─────────────────────────────────────────────────────────────

@referred_exam_bp.route('/student/referred-exam')
@login_required
def guide():
    if current_user.role != 'student':
        return redirect(url_for('index'))
    existing = ReferredExamRegistration.query.filter_by(user_id=current_user.id)\
                .order_by(ReferredExamRegistration.created_at.desc()).first()
    officer = get_referred_exam_officer()
    return render_template('student/referred_exam.html', registration=existing, officer=officer)


@referred_exam_bp.route('/student/referred-exam/submit', methods=['POST'])
@login_required
def submit():
    if current_user.role != 'student':
        return redirect(url_for('index'))

    uid = current_user.id
    existing = ReferredExamRegistration.query.filter_by(user_id=uid)\
                .order_by(ReferredExamRegistration.created_at.desc()).first()

    if existing and existing.status in ACTIVE_STATUSES:
        flash('You already have an active referred exam registration.', 'warning')
        return redirect(url_for('referred_exam.guide'))

    student_name   = request.form.get('student_name',   current_user.name).strip()
    student_id_num = request.form.get('student_id_num', '').strip()
    department     = request.form.get('department',     '').strip()

    courses = []
    for i in (1, 2, 3):
        code  = request.form.get(f'course{i}_code',  '').strip()
        title = request.form.get(f'course{i}_title', '').strip()
        if code:
            courses.append((code, title))

    if not student_id_num or not department:
        flash('Student ID and Department are required.', 'danger')
        return redirect(url_for('referred_exam.guide'))

    if not courses:
        flash('Add at least one course to register for the referred exam.', 'danger')
        return redirect(url_for('referred_exam.guide'))

    if len(courses) > 3:
        flash('You can register for a maximum of 3 courses.', 'danger')
        return redirect(url_for('referred_exam.guide'))

    officer = get_referred_exam_officer()

    # Pad out to exactly 3 slots
    while len(courses) < 3:
        courses.append((None, None))

    if existing and existing.status == 'Rejected':
        record = existing
        record.status       = 'Pending'
        record.officer_note = None
        record.updated_at   = datetime.now(timezone.utc)
        flash_msg = 'Registration resubmitted successfully! The registration officer will review it.'
    else:
        record = ReferredExamRegistration(user_id=uid)
        db.session.add(record)
        flash_msg = 'Referred exam registration submitted! The registration officer will process it and notify you.'

    record.student_name    = student_name
    record.student_id_num  = student_id_num
    record.department      = department
    record.officer_id      = officer.id if officer else None
    record.course1_code, record.course1_title = courses[0]
    record.course2_code, record.course2_title = courses[1]
    record.course3_code, record.course3_title = courses[2]

    db.session.commit()
    flash(flash_msg, 'success')
    return redirect(url_for('referred_exam.guide'))


# ── Officer side ─────────────────────────────────────────────────────────────

def _officer_can_manage():
    """True if the logged-in user may manage referred exam registrations —
    either they're the flagged officer, or an admin/super_admin."""
    if current_user.role in ('admin', 'super_admin'):
        return True
    if current_user.role == 'officer':
        rec = get_officer_record_for(current_user)
        return bool(rec and rec.handles_referred_exam)
    return False


@referred_exam_bp.route('/officer/referred-exam')
@login_required
def officer_dashboard():
    if not _officer_can_manage():
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))
    registrations = ReferredExamRegistration.query\
        .order_by(ReferredExamRegistration.created_at.desc()).all()
    return render_template('officer/referred_exam_dashboard.html', registrations=registrations)


@referred_exam_bp.route('/officer/referred-exam/<int:reg_id>')
@login_required
def detail(reg_id):
    if not _officer_can_manage():
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))
    registration = db.session.get(ReferredExamRegistration, reg_id)
    if not registration:
        flash('Registration not found.', 'danger')
        return redirect(url_for('referred_exam.officer_dashboard'))
    return render_template('officer/referred_exam_detail.html', registration=registration)


@referred_exam_bp.route('/officer/referred-exam/<int:reg_id>/update', methods=['POST'])
@login_required
def update_status(reg_id):
    if not _officer_can_manage():
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))

    registration = db.session.get(ReferredExamRegistration, reg_id)
    if not registration:
        flash('Registration not found.', 'danger')
        return redirect(url_for('referred_exam.officer_dashboard'))

    status = request.form.get('status', '').strip()
    note   = request.form.get('officer_note', '').strip()

    if status not in ('Pending', 'Ready', 'Collected', 'Rejected'):
        flash('Invalid status.', 'danger')
        return redirect(url_for('referred_exam.detail', reg_id=reg_id))

    prev_status = registration.status
    registration.status       = status
    registration.officer_note = note
    registration.updated_at   = datetime.now(timezone.utc)
    db.session.commit()

    if status != prev_status:
        status_msgs = {
            'Ready':     'Your referred exam paper is ready — come collect it!',
            'Rejected':  'Your referred exam registration was rejected.',
            'Collected': 'Your referred exam paper has been marked as collected.',
            'Pending':   'Your referred exam registration is pending review.',
        }
        db.session.add(Notification(
            user_id = registration.user_id,
            message = status_msgs.get(status, f'Your referred exam registration status changed to {status}.')
                      + (f' Note: {note}' if note else '')
        ))
        db.session.commit()

        if status in ('Ready', 'Rejected'):
            student = db.session.get(User, registration.user_id)
            if student:
                send_referred_exam_email(student, status, note, officer=registration.officer)

    flash(f'Registration marked {status}.', 'success')
    return redirect(url_for('referred_exam.officer_dashboard'))


@referred_exam_bp.route('/officer/referred-exam/<int:reg_id>/delete', methods=['POST'])
@login_required
def delete(reg_id):
    if not _officer_can_manage():
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))
    registration = db.session.get(ReferredExamRegistration, reg_id)
    if registration:
        db.session.delete(registration)
        db.session.commit()
        flash('Registration deleted.', 'success')
    return redirect(url_for('referred_exam.officer_dashboard'))


@referred_exam_bp.route('/officer/referred-exam/<int:reg_id>/pdf')
@login_required
def download_pdf(reg_id):
    """Printable PDF slip for the officer to download/print — includes
    signature lines for student, Head of Department, Registrar, and the
    registration officer, since the physical paper still needs wet signatures."""
    if not _officer_can_manage():
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))

    registration = db.session.get(ReferredExamRegistration, reg_id)
    if not registration:
        flash('Registration not found.', 'danger')
        return redirect(url_for('referred_exam.officer_dashboard'))

    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.graphics.shapes import Drawing, Circle, String
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from flask import current_app
    import io as _io
    import os

    # Register the Arabic-capable font once per process (falls back to
    # Helvetica gracefully if the font file isn't bundled yet).
    arabic_font = 'Helvetica'
    try:
        amiri_path = os.path.join(current_app.static_folder, 'fonts', 'Amiri-Regular.ttf')
        if os.path.exists(amiri_path):
            if 'Amiri' not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont('Amiri', amiri_path))
            arabic_font = 'Amiri'
    except Exception as _font_err:
        print(f'[IUT] Arabic font registration error (non-fatal): {_font_err}')

    def _arabic(text):
        try:
            import arabic_reshaper
            from bidi.algorithm import get_display
            return get_display(arabic_reshaper.reshape(text))
        except Exception:
            return text

    buf = _io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                             rightMargin=36, leftMargin=36,
                             topMargin=32, bottomMargin=28)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('RETitle', parent=styles['Heading1'],
                                  fontSize=14, alignment=TA_CENTER,
                                  textColor=colors.HexColor('#4c1d95'))
    sub_style = ParagraphStyle('RESub', parent=styles['Normal'],
                                fontSize=10, alignment=TA_CENTER,
                                textColor=colors.HexColor('#6b7280'))
    section_style = ParagraphStyle('RESection', parent=styles['Heading3'],
                                    fontSize=11, textColor=colors.HexColor('#4c1d95'),
                                    spaceBefore=14, spaceAfter=6)

    elements = []

    def _load_logo_flowable(filename, width, height):
        path = os.path.join(current_app.static_folder, filename)
        if not os.path.exists(path):
            return None
        from PIL import Image as PILImage
        buf = _io.BytesIO()
        with PILImage.open(path) as pil_img:
            pil_img = pil_img.convert('RGBA')
            pil_img.thumbnail((280, 200))
            pil_img.save(buf, format='PNG')
        buf.seek(0)
        return RLImage(buf, width=width, height=height)

    iut_logo = _load_logo_flowable('iut_logo.png', 78, 56)
    oic_logo = _load_logo_flowable('oic_logo.png', 78, 43)

    ar_style = ParagraphStyle('REArabic', fontName=arabic_font, fontSize=15,
                               alignment=TA_CENTER, textColor=colors.black, leading=19)
    fr_style = ParagraphStyle('REFrench', fontName='Helvetica-Oblique', fontSize=10,
                               alignment=TA_CENTER, textColor=colors.black, leading=13)
    en_style = ParagraphStyle('REEnglish', fontName='Helvetica', fontSize=12,
                               alignment=TA_CENTER, textColor=colors.black, leading=15)
    place_style = ParagraphStyle('REPlace', fontName='Helvetica', fontSize=11,
                                  alignment=TA_CENTER, textColor=colors.black, leading=14)
    oic_line_style = ParagraphStyle('REOicLine', fontName='Helvetica-Bold', fontSize=11.5,
                                     alignment=TA_CENTER, textColor=colors.black, leading=14)

    header_title = [
        Paragraph(_arabic("الجامعة الإسلامية للتكنولوجيا"), ar_style),
        Paragraph("UNIVERSITE ISLAMIQUE DE TECHNOLOGIE", fr_style),
        Paragraph("ISLAMIC UNIVERSITY OF TECHNOLOGY", en_style),
        Paragraph("DHAKA, BANGLADESH", place_style),
        Paragraph("ORGANISATION OF ISLAMIC COOPERATION", oic_line_style),
    ]

    header_t = Table(
        [[iut_logo or '', header_title, oic_logo or '']],
        colWidths=[90, 335, 90]
    )
    header_t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN',  (0, 0), (0, 0), 'LEFT'),
        ('ALIGN',  (1, 0), (1, 0), 'CENTER'),
        ('ALIGN',  (2, 0), (2, 0), 'RIGHT'),
    ]))
    elements.append(header_t)
    elements.append(Spacer(1, 8))
    elements.append(Paragraph("Referred Exam Registration Form", title_style))
    elements.append(Spacer(1, 2))

    elements.append(Paragraph(
        f"Registration #{registration.id} &nbsp;|&nbsp; Status: {registration.status} "
        f"&nbsp;|&nbsp; Generated: {datetime.now(timezone.utc).strftime('%d %b %Y %H:%M')} UTC",
        sub_style
    ))

    elements.append(Paragraph("Student Information", section_style))
    student_data = [
        ['Full Name',    registration.student_name],
        ['Student ID',   registration.student_id_num],
        ['Department',   registration.department],
        ['Submitted On', registration.created_at.strftime('%d %b %Y, %I:%M %p')],
    ]
    st = Table(student_data, colWidths=[130, 360])
    st.setStyle(TableStyle([
        ('FONTNAME',  (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE',  (0, 0), (-1, -1), 9.5),
        ('BACKGROUND',(0, 0), (0, -1), colors.HexColor('#f5f3ff')),
        ('GRID',      (0, 0), (-1, -1), 0.5, colors.HexColor('#dee2e6')),
        ('PADDING',   (0, 0), (-1, -1), 7),
    ]))
    elements.append(st)

    elements.append(Paragraph("Courses Registered for Referred Exam", section_style))
    course_rows = [['#', 'Course Code', 'Course Title']]
    for i, c in enumerate(registration.course_list(), 1):
        course_rows.append([str(i), c['code'], c['title'] or '—'])
    while len(course_rows) < 4:  # pad to always show 3 rows
        course_rows.append([str(len(course_rows)), '', ''])

    ct = Table(course_rows, colWidths=[25, 110, 355])
    ct.setStyle(TableStyle([
        ('BACKGROUND',      (0, 0), (-1, 0), colors.HexColor('#4c1d95')),
        ('TEXTCOLOR',       (0, 0), (-1, 0), colors.white),
        ('FONTNAME',        (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',        (0, 0), (-1, -1), 9.5),
        ('ROWBACKGROUNDS',  (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
        ('GRID',            (0, 0), (-1, -1), 0.5, colors.HexColor('#dee2e6')),
        ('PADDING',         (0, 0), (-1, -1), 7),
    ]))
    elements.append(ct)

    if registration.officer_note:
        elements.append(Paragraph("Officer's Note", section_style))
        elements.append(Paragraph(registration.officer_note, styles['Normal']))

    elements.append(Spacer(1, 30))
    elements.append(Paragraph("Signatures", section_style))
    elements.append(Paragraph(
        "To be signed by hand after printing.",
        ParagraphStyle('RESigNote', parent=styles['Normal'], fontSize=8.5,
                        textColor=colors.HexColor('#6b7280'))
    ))
    elements.append(Spacer(1, 6))

    sig_labels = [
        'Student Signature',
        'Head of Department Signature',
        'Registrar Signature',
        'Registration Officer (Md. Enamul Hoque)',
    ]

    registrar_sig_img = _load_logo_flowable('registrar_signature.png', 62, 48)

    sig_rows = []
    for idx, label in enumerate(sig_labels):
        sig_rows.append([label, '', 'Date:', ''])
        box_content = registrar_sig_img if (idx == 2 and registrar_sig_img) else ''
        sig_rows.append(['', box_content, '', ''])  # blank signing space, sits above the line

    sig_t = Table(sig_rows, colWidths=[190, 160, 30, 130],
                   rowHeights=[16, 34] * len(sig_labels))
    sig_style = [
        ('FONTSIZE',   (0, 0), (-1, -1), 9),
        ('VALIGN',     (0, 0), (-1, -1), 'BOTTOM'),
        ('ALIGN',      (1, 0), (1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
    ]
    for i in range(len(sig_labels)):
        box_row = i * 2 + 1
        sig_style.append(('LINEBELOW', (1, box_row), (1, box_row), 0.7, colors.black))
        sig_style.append(('LINEBELOW', (3, box_row), (3, box_row), 0.7, colors.black))
    sig_t.setStyle(TableStyle(sig_style))
    elements.append(sig_t)

    # IUT's official seal — not tied to any one signee, so it sits centered
    # underneath the whole signature block, sized to actually read as a seal.
    seal_img = _load_logo_flowable('registrar_seal.png', 140, 100)
    if seal_img:
        seal_img.hAlign = 'CENTER'
        stamp_visual = seal_img
    else:
        stamp_visual = Drawing(140, 140)
        stamp_visual.add(Circle(70, 73, 60, strokeColor=colors.HexColor('#9ca3af'),
                                 strokeWidth=1, strokeDashArray=(3, 2), fillColor=None))
        stamp_visual.add(String(70, 77, "OFFICIAL", fontSize=9, fillColor=colors.HexColor('#9ca3af'),
                                 textAnchor='middle'))
        stamp_visual.add(String(70, 64, "SEAL", fontSize=9, fillColor=colors.HexColor('#9ca3af'),
                                 textAnchor='middle'))
        stamp_visual.hAlign = 'CENTER'

    stamp_caption = Paragraph(
        "Official Seal — Islamic University of Technology (IUT)",
        ParagraphStyle('REStampCap', parent=styles['Normal'], fontSize=8.5,
                        alignment=TA_CENTER, textColor=colors.HexColor('#6b7280'))
    )

    elements.append(Spacer(1, 18))
    elements.append(stamp_visual)
    elements.append(Spacer(1, 4))
    elements.append(stamp_caption)

    if registrar_sig_img or seal_img:
        elements.append(Spacer(1, 6))
        elements.append(Paragraph(
            "The Registrar's signature and the IUT seal above are digitally "
            "pre-authorized and applied automatically — no physical stamping "
            "required for this section.",
            ParagraphStyle('REAutoNote', parent=styles['Normal'], fontSize=7.5,
                            alignment=TA_CENTER, textColor=colors.HexColor('#9ca3af'))
        ))

    elements.append(Spacer(1, 20))
    elements.append(Paragraph(
        "This form was generated by the IUT University Appointment Management System.",
        ParagraphStyle('REFooter', parent=styles['Normal'], fontSize=8,
                        alignment=TA_CENTER, textColor=colors.HexColor('#9ca3af'))
    ))

    doc.build(elements)
    buf.seek(0)
    filename = f"referred_exam_{registration.student_id_num}_{registration.id}.pdf"
    return Response(buf, mimetype='application/pdf',
                     headers={'Content-Disposition': f'attachment; filename={filename}'})
