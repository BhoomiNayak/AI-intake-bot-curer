"""
Curer Pre-Consultation AI Intake Bot
Email sender module — sends HTML briefing card + PDF attachment via Gmail SMTP.

Security features:
- Email validation (RFC 5322 pattern + domain check)
- Rate limiting (max 3 emails per session, cooldown between sends)
- Input sanitization (HTML escaping in email body)
"""

import html
import os
import re
import smtplib
import time
from datetime import datetime
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import streamlit as st

# --- Security Constants ---
MAX_EMAILS_PER_SESSION = 3
EMAIL_COOLDOWN_SECONDS = 30  # Minimum seconds between sends
MAX_EMAIL_LENGTH = 254  # RFC 5321 max email length

# RFC 5322 simplified email pattern
EMAIL_REGEX = re.compile(
    r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9]"
    r"(?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
    r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$"
)

# Blocked domains (disposable/temporary email services)
BLOCKED_DOMAINS = {
    "tempmail.com", "throwaway.email", "guerrillamail.com",
    "mailinator.com", "yopmail.com", "10minutemail.com",
    "trashmail.com", "fakeinbox.com",
}


def validate_email(email: str) -> tuple[bool, str]:
    """
    Validate an email address for format, length, and domain safety.

    Returns (is_valid, error_message).
    """
    if not email:
        return False, "Email address is required."

    email = email.strip().lower()

    if len(email) > MAX_EMAIL_LENGTH:
        return False, f"Email exceeds maximum length of {MAX_EMAIL_LENGTH} characters."

    if not EMAIL_REGEX.match(email):
        return False, "Invalid email format. Please enter a valid email address."

    # Check domain
    domain = email.split("@")[1]
    if domain in BLOCKED_DOMAINS:
        return False, "Disposable email addresses are not allowed."

    # Must have at least one dot in domain
    if "." not in domain:
        return False, "Invalid email domain."

    return True, ""


def check_rate_limit() -> tuple[bool, str]:
    """
    Check if the current session is within email rate limits.

    Returns (allowed, error_message).
    """
    if "email_send_count" not in st.session_state:
        st.session_state.email_send_count = 0
    if "last_email_time" not in st.session_state:
        st.session_state.last_email_time = 0

    # Check max sends per session
    if st.session_state.email_send_count >= MAX_EMAILS_PER_SESSION:
        return False, f"Rate limit reached. Maximum {MAX_EMAILS_PER_SESSION} emails per session."

    # Check cooldown
    elapsed = time.time() - st.session_state.last_email_time
    if elapsed < EMAIL_COOLDOWN_SECONDS and st.session_state.email_send_count > 0:
        remaining = int(EMAIL_COOLDOWN_SECONDS - elapsed)
        return False, f"Please wait {remaining} seconds before sending again."

    return True, ""


def record_email_sent():
    """Record that an email was sent (for rate limiting)."""
    st.session_state.email_send_count = st.session_state.get("email_send_count", 0) + 1
    st.session_state.last_email_time = time.time()


def sanitize_text(text: str) -> str:
    """Sanitize text for safe HTML insertion — escape HTML entities."""
    if not text:
        return ""
    return html.escape(str(text), quote=True)


def get_email_credentials() -> tuple[str, str]:
    """Retrieve Gmail credentials from st.secrets or environment variables."""
    try:
        address = st.secrets["GMAIL_ADDRESS"]
    except (KeyError, FileNotFoundError):
        address = os.environ.get("GMAIL_ADDRESS", "")

    try:
        password = st.secrets["GMAIL_APP_PASSWORD"]
    except (KeyError, FileNotFoundError):
        password = os.environ.get("GMAIL_APP_PASSWORD", "")

    return address, password


def get_doctor_email() -> str:
    """Retrieve doctor's email from st.secrets or environment variables."""
    try:
        return st.secrets["DOCTOR_EMAIL"]
    except (KeyError, FileNotFoundError):
        return os.environ.get("DOCTOR_EMAIL", "")


def build_html_email(intake_data: dict, specialty: str) -> str:
    """Build an HTML email body with inline CSS. All user content is sanitized."""

    # Sanitize all user-provided data
    patient_summary = sanitize_text(intake_data.get("patient_summary", "No summary available"))
    chief_complaint = sanitize_text(intake_data.get("chief_complaint", "Not specified"))
    symptoms = [sanitize_text(s) for s in intake_data.get("symptoms", []) if s]
    duration = sanitize_text(intake_data.get("duration", "Not specified"))
    severity = sanitize_text(intake_data.get("severity", "Not assessed"))
    relevant_history = sanitize_text(intake_data.get("relevant_history", "None reported"))
    red_flags = [sanitize_text(rf) for rf in intake_data.get("red_flags", []) if rf]
    focus_areas = [sanitize_text(fa) for fa in intake_data.get("suggested_focus_areas", []) if fa]
    specialty_safe = sanitize_text(specialty)

    timestamp = datetime.now().strftime("%B %d, %Y at %I:%M %p")

    # Severity color
    severity_lower = severity.lower()
    if "severe" in severity_lower or "high" in severity_lower:
        severity_bg = "#FEE2E2"
        severity_color = "#DC2626"
    elif "moderate" in severity_lower or "medium" in severity_lower:
        severity_bg = "#FEF3C7"
        severity_color = "#92400E"
    else:
        severity_bg = "#D1FAE5"
        severity_color = "#065F46"

    # Build symptom pills
    symptom_html = ""
    if symptoms:
        for s in symptoms:
            symptom_html += (
                f'<span style="background-color:#CCFBF1;color:#0F766E;'
                f'padding:4px 10px;border-radius:15px;font-size:13px;'
                f'font-weight:500;margin-right:6px;display:inline-block;margin-bottom:4px;">{s}</span>'
            )
    else:
        symptom_html = '<span style="color:#6B7280;">None reported</span>'

    # Build red flags
    red_flag_html = ""
    if red_flags and any(rf.strip() for rf in red_flags if rf.lower() != "none"):
        red_flag_html = '<tr><td style="padding:12px 0;border-bottom:1px solid #F3F4F6;">'
        red_flag_html += '<div style="color:#0D9488;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px;">RED FLAGS</div>'
        for rf in red_flags:
            if rf.strip() and rf.lower() != "none":
                red_flag_html += (
                    f'<span style="background-color:#FEE2E2;color:#DC2626;'
                    f'padding:4px 10px;border-radius:15px;font-size:13px;'
                    f'font-weight:500;margin-right:6px;display:inline-block;margin-bottom:4px;">{rf}</span>'
                )
        red_flag_html += '</td></tr>'

    # Build focus areas
    focus_html = ""
    if focus_areas:
        for fa in focus_areas:
            focus_html += (
                f'<span style="background-color:#CCFBF1;color:#0F766E;'
                f'padding:4px 10px;border-radius:15px;font-size:13px;'
                f'font-weight:500;margin-right:6px;display:inline-block;margin-bottom:4px;">{fa}</span>'
            )
    else:
        focus_html = '<span style="color:#6B7280;">General assessment recommended</span>'

    email_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="margin:0;padding:0;background-color:#F9FAFB;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
        <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#F9FAFB;padding:20px;">
            <tr>
                <td align="center">
                    <table width="600" cellpadding="0" cellspacing="0" style="background-color:#FFFFFF;border-radius:12px;border:2px solid #0D9488;overflow:hidden;">
                        <!-- Header -->
                        <tr>
                            <td style="background-color:#0D9488;padding:20px;text-align:center;">
                                <h1 style="color:#FFFFFF;margin:0;font-size:22px;">Curer</h1>
                                <p style="color:#CCFBF1;margin:4px 0 0 0;font-size:14px;">Pre-Consultation Briefing Card</p>
                            </td>
                        </tr>

                        <!-- Specialty Badge -->
                        <tr>
                            <td style="padding:20px 24px 0 24px;">
                                <span style="background-color:#0D9488;color:#FFFFFF;padding:5px 14px;border-radius:20px;font-size:13px;font-weight:500;">{specialty_safe}</span>
                            </td>
                        </tr>

                        <!-- Content -->
                        <tr>
                            <td style="padding:16px 24px;">
                                <table width="100%" cellpadding="0" cellspacing="0">
                                    <tr>
                                        <td style="padding:12px 0;border-bottom:1px solid #F3F4F6;">
                                            <div style="color:#0D9488;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px;">Patient Summary</div>
                                            <div style="color:#1F2937;font-size:15px;line-height:1.5;">{patient_summary}</div>
                                        </td>
                                    </tr>
                                    <tr>
                                        <td style="padding:12px 0;border-bottom:1px solid #F3F4F6;">
                                            <div style="color:#0D9488;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px;">Chief Complaint</div>
                                            <div style="color:#1F2937;font-size:15px;line-height:1.5;">{chief_complaint}</div>
                                        </td>
                                    </tr>
                                    <tr>
                                        <td style="padding:12px 0;border-bottom:1px solid #F3F4F6;">
                                            <div style="color:#0D9488;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px;">Symptoms</div>
                                            <div>{symptom_html}</div>
                                        </td>
                                    </tr>
                                    <tr>
                                        <td style="padding:12px 0;border-bottom:1px solid #F3F4F6;">
                                            <div style="color:#0D9488;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px;">Duration</div>
                                            <div style="color:#1F2937;font-size:15px;">{duration}</div>
                                        </td>
                                    </tr>
                                    <tr>
                                        <td style="padding:12px 0;border-bottom:1px solid #F3F4F6;">
                                            <div style="color:#0D9488;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px;">Severity</div>
                                            <span style="background-color:{severity_bg};color:{severity_color};padding:4px 12px;border-radius:6px;font-weight:600;font-size:14px;">{severity}</span>
                                        </td>
                                    </tr>
                                    <tr>
                                        <td style="padding:12px 0;border-bottom:1px solid #F3F4F6;">
                                            <div style="color:#0D9488;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px;">Relevant History</div>
                                            <div style="color:#1F2937;font-size:15px;line-height:1.5;">{relevant_history}</div>
                                        </td>
                                    </tr>
                                    {red_flag_html}
                                    <tr>
                                        <td style="padding:12px 0;">
                                            <div style="color:#0D9488;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px;">Suggested Focus Areas</div>
                                            <div>{focus_html}</div>
                                        </td>
                                    </tr>
                                </table>
                            </td>
                        </tr>

                        <!-- Footer -->
                        <tr>
                            <td style="background-color:#F0FDFA;padding:16px 24px;text-align:center;border-top:1px solid #CCFBF1;">
                                <p style="color:#9CA3AF;font-size:12px;margin:0;">
                                    Generated by Curer AI Intake &bull; {timestamp}
                                </p>
                                <p style="color:#9CA3AF;font-size:11px;margin:4px 0 0 0;">
                                    This is an AI-generated pre-consultation summary, not a medical diagnosis.
                                </p>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """
    return email_html


def send_briefing_email(
    recipient: str,
    intake_data: dict,
    specialty: str,
    pdf_bytes: bytes,
) -> bool:
    """
    Send the briefing card as an HTML email with PDF attachment.

    Security checks performed:
    1. Email validation (format, length, blocked domains)
    2. Rate limiting (max sends per session, cooldown)
    3. Input sanitization (HTML escaping)

    Returns True on success, raises Exception on failure.
    """
    # --- Security: Validate recipient ---
    is_valid, error_msg = validate_email(recipient)
    if not is_valid:
        raise ValueError(f"Invalid recipient: {error_msg}")

    # --- Security: Rate limiting ---
    allowed, rate_msg = check_rate_limit()
    if not allowed:
        raise ValueError(rate_msg)

    # --- Get credentials ---
    sender_address, app_password = get_email_credentials()

    if not sender_address or not app_password:
        raise ValueError(
            "Gmail credentials not configured. Set GMAIL_ADDRESS and GMAIL_APP_PASSWORD "
            "in .streamlit/secrets.toml or as environment variables."
        )

    # --- Build message ---
    msg = MIMEMultipart("mixed")
    msg["From"] = f"Curer AI Intake Bot <{sender_address}>"
    msg["To"] = recipient
    msg["Subject"] = f"Pre-Consultation Briefing Card - {sanitize_text(specialty)}"

    # HTML body (content already sanitized inside build_html_email)
    html_body = build_html_email(intake_data, specialty)
    html_part = MIMEText(html_body, "html")
    msg.attach(html_part)

    # PDF attachment
    safe_specialty = re.sub(r"[^a-z0-9_]", "", specialty.lower().replace(" ", "_"))
    pdf_filename = f"curer_briefing_{safe_specialty}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    pdf_part = MIMEApplication(pdf_bytes, _subtype="pdf")
    pdf_part.add_header("Content-Disposition", "attachment", filename=pdf_filename)
    msg.attach(pdf_part)

    # --- Send via Gmail SMTP ---
    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(sender_address, app_password)
            server.sendmail(sender_address, recipient, msg.as_string())
    except smtplib.SMTPAuthenticationError:
        raise ValueError(
            "SMTP authentication failed. Check your GMAIL_ADDRESS and GMAIL_APP_PASSWORD."
        )
    except smtplib.SMTPRecipientsRefused:
        raise ValueError(f"Recipient address rejected: {recipient}")
    except smtplib.SMTPException as e:
        raise RuntimeError(f"SMTP error: {str(e)}")
    except TimeoutError:
        raise RuntimeError("Connection to Gmail SMTP timed out. Please try again.")

    # Record successful send for rate limiting
    record_email_sent()
    return True
