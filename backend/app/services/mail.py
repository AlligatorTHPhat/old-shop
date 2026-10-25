import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger(__name__)

OTP_TEMPLATE = """Chào bạn,

Chúng tôi đã nhận được yêu cầu đặt lại mật khẩu cho tài khoản của bạn tại {project}.

Mã OTP của bạn là:

        {otp}

Mã có hiệu lực trong 5 phút và chỉ dùng được một lần. Vui lòng không chia sẻ mã này cho bất kỳ ai.
Nếu bạn không thực hiện yêu cầu này, hãy bỏ qua email.

Trân trọng,
Đội ngũ {project}
"""


def send_email(to: str, subject: str, body: str) -> bool:
    if not settings.SMTP_USER:
        logger.warning("SMTP is not configured, email was not sent")
        return False

    msg = EmailMessage()
    msg["From"] = settings.SMTP_USER
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        context = ssl.create_default_context()
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
        with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, context=context) as smtp:
            smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            smtp.send_message(msg)
        return True
    except (smtplib.SMTPException, OSError):
        logger.exception("Failed to send email")
        return False


def send_otp_email(email_to: str, otp: str) -> bool:
    return send_email(
        to=email_to,
        subject=f"[{settings.PROJECT_NAME}] Mã xác thực OTP",
        body=OTP_TEMPLATE.format(project=settings.PROJECT_NAME, otp=otp),
    )
