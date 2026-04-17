import logging
import smtplib
from email.message import EmailMessage

from config import get_settings

log = logging.getLogger("api.email")


class EmailDeliveryError(RuntimeError):
    pass


def _is_email_configured() -> bool:
    settings = get_settings()
    return bool(settings.smtp_host and settings.smtp_from_email)


def send_email(*, to_email: str, subject: str, text_body: str, html_body: str | None = None) -> None:
    settings = get_settings()

    if not _is_email_configured():
        raise EmailDeliveryError(
            "Email service is not configured. Set SMTP_HOST and SMTP_FROM_EMAIL."
        )

    message = EmailMessage()
    sender = settings.smtp_from_email
    if settings.smtp_from_name:
        sender = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"

    message["From"] = sender
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(text_body)

    if html_body:
        message.add_alternative(html_body, subtype="html")

    try:
        if settings.smtp_use_ssl:
            server: smtplib.SMTP = smtplib.SMTP_SSL(
                settings.smtp_host,
                settings.smtp_port,
                timeout=20,
            )
        else:
            server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20)

        with server:
            if not settings.smtp_use_ssl:
                server.ehlo()
                if settings.smtp_use_tls:
                    server.starttls()
                    server.ehlo()

            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)

            server.send_message(message)
            log.info("Email sent successfully to %s", to_email)
    except Exception as exc:
        log.exception("Failed to send email to %s", to_email)
        raise EmailDeliveryError("Failed to deliver email") from exc


def email_configured() -> bool:
    return _is_email_configured()
