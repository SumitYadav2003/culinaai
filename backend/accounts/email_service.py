import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.urls import reverse
from django.utils.html import escape


logger = logging.getLogger(__name__)


def send_welcome_email(request, user):
    """
    Sends a welcome email after successful user registration.

    Important:
    - This function should not break signup if email sending fails.
    - It supports both real SMTP email and console email backend.
    - Email settings are controlled from settings.py and .env.
    """

    if not user.email:
        return False

    full_name = user.get_full_name().strip() or user.username
    login_url = request.build_absolute_uri(reverse("login"))

    subject = "Welcome to CulinaAI"

    plain_message = f"""
Hi {full_name},

Welcome to CulinaAI. Your account is ready.

Tell CulinaAI what's in your kitchen and it will make a recipe that fits your diet and allergies, with the nutrition and cost worked out. You can save recipes, keep a pantry list and cook step by step.

Log in here:
{login_url}

CulinaAI
""".strip()

    html_message = f"""
<!doctype html>
<html>
<head>
    <meta charset="utf-8">
</head>
<body style="margin:0; padding:0; background:#f5f7f5; font-family:Arial, Helvetica, sans-serif; color:#1e221e;">
    <table width="100%" cellpadding="0" cellspacing="0" role="presentation" style="background:#f5f7f5; padding:32px 12px;">
        <tr>
            <td align="center">
                <table width="100%" cellpadding="0" cellspacing="0" role="presentation" style="max-width:560px; background:#ffffff; border:1px solid #dfe3df; border-radius:12px;">
                    <tr>
                        <td style="padding:32px;">
                            <p style="margin:0 0 20px; color:#1f4d2b; font-size:15px; font-weight:bold;">CulinaAI</p>
                            <h1 style="margin:0 0 16px; font-size:24px; line-height:1.3;">Welcome, {escape(full_name)}</h1>
                            <p style="margin:0 0 16px; font-size:16px; line-height:1.6; color:#3d453d;">
                                Your account is ready. Tell CulinaAI what's in your kitchen and it will make a recipe
                                that fits your diet and allergies, with the nutrition and cost worked out.
                            </p>
                            <p style="margin:28px 0;">
                                <a href="{login_url}" style="display:inline-block; background:#1f4d2b; color:#ffffff; text-decoration:none; padding:12px 24px; border-radius:8px; font-weight:bold; font-size:16px;">Log in</a>
                            </p>
                            <p style="margin:0; font-size:13px; line-height:1.6; color:#576557;">
                                If the button doesn't work, copy this link into your browser:<br>
                                <span style="word-break:break-all;">{login_url}</span>
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
""".strip()

    try:
        email = EmailMultiAlternatives(
            subject=subject,
            body=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
        )

        email.attach_alternative(html_message, "text/html")
        email.send(fail_silently=False)

        return True

    except Exception as error:
        logger.exception("Failed to send welcome email to %s", user.email)
        print("CULINAAI WELCOME EMAIL ERROR:", repr(error))
        return False