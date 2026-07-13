import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.urls import reverse


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

Welcome to CulinaAI!

Your account has been created successfully. You can now log in to generate personalised recipes, save your favourite meals, and manage your recipe history.

Login here:
{login_url}

Regards,
CulinaAI Team
""".strip()

    html_message = f"""
<!doctype html>
<html>
<head>
    <meta charset="utf-8">
</head>
<body style="margin:0; padding:0; background:#f6f3ef; font-family:Arial, sans-serif;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background:#f6f3ef; padding:30px 0;">
        <tr>
            <td align="center">
                <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff; border-radius:18px; overflow:hidden; box-shadow:0 12px 35px rgba(0,0,0,0.08);">
                    <tr>
                        <td style="background:linear-gradient(135deg,#f28c28,#f7c948); padding:28px; text-align:center;">
                            <h1 style="margin:0; color:#1f1b16; font-size:30px;">
                                Welcome to CulinaAI
                            </h1>
                            <p style="margin:8px 0 0; color:#2b241d; font-size:16px;">
                                Your AI-assisted cooking journey starts here.
                            </p>
                        </td>
                    </tr>

                    <tr>
                        <td style="padding:32px;">
                            <h2 style="margin:0 0 12px; color:#1f1b16;">
                                Hi {full_name},
                            </h2>

                            <p style="font-size:16px; line-height:1.6; color:#4f4a45;">
                                Your CulinaAI account has been created successfully.
                                You can now log in to generate personalised recipes,
                                save your favourite meals, and manage your recipe history.
                            </p>

                            <div style="text-align:center; margin:32px 0;">
                                <a href="{login_url}"
                                   style="display:inline-block; background:#f28c28; color:#ffffff; text-decoration:none; padding:14px 28px; border-radius:999px; font-weight:bold; font-size:16px;">
                                    Login to CulinaAI
                                </a>
                            </div>

                            <p style="font-size:14px; line-height:1.6; color:#777;">
                                If the button does not work, copy and paste this link into your browser:
                            </p>

                            <p style="font-size:14px; line-height:1.6; color:#f28c28; word-break:break-all;">
                                {login_url}
                            </p>

                            <p style="font-size:16px; line-height:1.6; color:#4f4a45; margin-top:28px;">
                                Regards,<br>
                                <strong>CulinaAI Team</strong>
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