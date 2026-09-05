import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from app.core.celery_app import celery_app
from app.core.config import settings

logger = logging.getLogger(__name__)

BRAND_COLOR = "#4F46E5"


def render_email(
    heading: str,
    body_html: str,
    button_label: Optional[str] = None,
    button_url: Optional[str] = None,
    accent: str = BRAND_COLOR,
) -> str:
    """Wraps message specific content in the shared HTML email chrome."""
    button = ""
    if button_label and button_url:
        button = f"""
        <p style="margin: 24px 0;">
          <a href="{button_url}" style="background-color: {accent}; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: 600; display: inline-block;">{button_label}</a>
        </p>
        <p style="font-size: 12px; color: #888;">If the button does not work, paste this link into your browser:<br />{button_url}</p>
        """

    return f"""
    <html>
      <body style="font-family: -apple-system, Segoe UI, Roboto, Arial, sans-serif; line-height: 1.6; color: #333; background-color: #f6f7f9; padding: 24px;">
        <div style="max-width: 560px; margin: 0 auto; background: #ffffff; border-radius: 12px; padding: 32px; border: 1px solid #e5e7eb;">
          <h2 style="color: {accent}; margin-top: 0;">{heading}</h2>
          {body_html}
          {button}
          <hr style="border: none; border-top: 1px solid #eee; margin: 24px 0;" />
          <p style="font-size: 12px; color: #888;">This is an automated message from {settings.EMAILS_FROM_NAME}.</p>
        </div>
      </body>
    </html>
    """


def send_email(recipient: str, subject: str, html_content: str) -> str:
    """Helper method to send an HTML email using SMTP or log it if SMTP configuration is missing."""
    smtp_configured = all(
        [
            settings.SMTP_HOST,
            settings.SMTP_PORT,
            settings.SMTP_USER,
            settings.SMTP_PASSWORD,
        ]
    )

    if not smtp_configured:
        logger.info("=== [MOCK EMAIL DISPATCHED] ===")
        logger.info(f"Recipient: {recipient}")
        logger.info(f"Subject:   {subject}")
        logger.info("--- CONTENT ---")
        logger.info(html_content.strip())
        logger.info("==============================")
        return f"Mock email dispatched to {recipient}"

    # Build standard SMTP mime message
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{settings.EMAILS_FROM_NAME} <{settings.EMAILS_FROM_EMAIL}>"
    msg["To"] = recipient
    msg.attach(MIMEText(html_content, "html"))

    try:
        # Connect, secure via TLS, login and send
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:  # type: ignore
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)  # type: ignore
            server.sendmail(
                settings.EMAILS_FROM_EMAIL, recipient, msg.as_string()  # type: ignore
            )
        logger.info(f"Real email successfully sent to: {recipient}")
        return f"Real email sent to {recipient}"
    except Exception as e:
        logger.error(f"Failed to send real email to {recipient} via SMTP: {e}")
        raise e


@celery_app.task(name="app.tasks.email_tasks.send_verification_email")
def send_verification_email(email: str, token: str, full_name: str = "") -> str:
    """Celery task to send email verification links asynchronously."""
    # Links point at the frontend, which calls the API and renders the result.
    link = f"{settings.FRONTEND_URL}/verify-email?token={token}"
    html = render_email(
        heading="Verify your email address",
        body_html=(
            f"<p>Hi {full_name or 'there'},</p>"
            "<p>Thanks for signing up. Confirm your email address to activate your account.</p>"
            f"<p style='font-size: 13px; color: #666;'>This link expires in {settings.EMAIL_VERIFICATION_EXPIRE_HOURS} hours. "
            "If you did not create an account, you can safely ignore this email.</p>"
        ),
        button_label="Verify email",
        button_url=link,
    )
    return send_email(email, "Verify your email address", html)


@celery_app.task(name="app.tasks.email_tasks.send_welcome_email")
def send_welcome_email(email: str, full_name: str = "") -> str:
    """Celery task to send a welcome email after verification."""
    html = render_email(
        heading="Welcome aboard!",
        body_html=(
            f"<p>Hi {full_name or 'there'},</p>"
            "<p>Your email is verified and your account is fully active. "
            "You can sign in and start exploring.</p>"
        ),
        button_label="Sign in",
        button_url=f"{settings.FRONTEND_URL}/login",
        accent="#10B981",
    )
    return send_email(email, f"Welcome to {settings.EMAILS_FROM_NAME}!", html)


@celery_app.task(name="app.tasks.email_tasks.send_password_reset_email")
def send_password_reset_email(email: str, token: str, full_name: str = "") -> str:
    """Celery task to send a password reset link asynchronously."""
    link = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    html = render_email(
        heading="Reset your password",
        body_html=(
            f"<p>Hi {full_name or 'there'},</p>"
            "<p>We received a request to reset your password. Choose a new one using the button below.</p>"
            f"<p style='font-size: 13px; color: #666;'>This link expires in {settings.PASSWORD_RESET_EXPIRE_MINUTES} minutes. "
            "If you did not request a reset, no action is needed and your password stays unchanged.</p>"
        ),
        button_label="Reset password",
        button_url=link,
    )
    return send_email(email, "Reset your password", html)
