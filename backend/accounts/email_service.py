import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.html import escape
from django.utils.http import urlsafe_base64_encode

from .tokens import email_confirm_token


logger = logging.getLogger(__name__)


def confirm_email_url(request, user):
    """The link in the confirmation email. Opening it confirms the address."""

    uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
    token = email_confirm_token.make_token(user)
    return request.build_absolute_uri(reverse("confirm_email", args=[uidb64, token]))


def build_branded_html(heading, paragraphs, button_text, button_url, small_print="", small_link=None):
    """
    The HTML layout shared by CulinaAI emails. Everything passed in is escaped here.
    small_print and small_link (link text, url) go under the button, e.g. "Turn this email off".
    """

    body = "".join(
        f'<p style="margin:0 0 16px; font-size:16px; line-height:1.6; color:#3d453d;">{escape(text)}</p>'
        for text in paragraphs
    )
    url = escape(button_url)
    extra = ""
    if small_print or small_link:
        link = (
            f' <a href="{escape(small_link[1])}" style="color:#1f4d2b;">{escape(small_link[0])}</a>'
            if small_link else ""
        )
        extra = (
            f'<p style="margin:20px 0 0; font-size:13px; line-height:1.6; color:#576557;">'
            f"{escape(small_print)}{link}</p>"
        )

    return f"""
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
                            <h1 style="margin:0 0 16px; font-size:24px; line-height:1.3;">{escape(heading)}</h1>
                            {body}
                            <p style="margin:28px 0;">
                                <a href="{url}" style="display:inline-block; background:#1f4d2b; color:#ffffff; text-decoration:none; padding:12px 24px; border-radius:8px; font-weight:bold; font-size:16px;">{escape(button_text)}</a>
                            </p>
                            <p style="margin:0; font-size:13px; line-height:1.6; color:#576557;">
                                If the button doesn't work, copy this link into your browser:<br>
                                <span style="word-break:break-all;">{url}</span>
                            </p>
                            {extra}
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
""".strip()


def send_email(to, subject, plain_message, html_message, kind, headers=None):
    """Sends one email. Returns False instead of raising, so a mail problem never breaks a page."""

    try:
        email = EmailMultiAlternatives(
            subject=subject,
            body=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[to],
            headers=headers or {},
        )
        email.attach_alternative(html_message, "text/html")
        email.send(fail_silently=False)
        return True
    except Exception:
        logger.exception("Couldn't send the %s email to user address ending %s", kind, to.split("@")[-1])
        return False


def send_welcome_email(request, user, confirm=False):
    """
    The email sent after signing up. When confirm is True it carries the link
    that confirms the email address; otherwise it links to the login page.
    """

    if not user.email:
        return False

    full_name = user.get_full_name().strip() or user.username
    intro = (
        "Tell CulinaAI what's in your kitchen and it will make a recipe that fits your diet "
        "and allergies, with the nutrition and cost worked out."
    )

    if confirm:
        link = confirm_email_url(request, user)
        paragraphs = [
            "Your account is ready. " + intro,
            "Before you make your first recipe, confirm this is your email address. The link works for 3 days.",
        ]
        button_text = "Confirm my email"
        plain_link_line = "Confirm your email here (the link works for 3 days):"
    else:
        link = request.build_absolute_uri(reverse("login"))
        paragraphs = ["Your account is ready. " + intro]
        button_text = "Log in"
        plain_link_line = "Log in here:"

    plain_message = "\n\n".join(
        [f"Hi {full_name},", *paragraphs, f"{plain_link_line}\n{link}", "CulinaAI"]
    )
    html_message = build_branded_html(f"Welcome, {full_name}", paragraphs, button_text, link)

    return send_email(user.email, "Welcome to CulinaAI", plain_message, html_message, "welcome")


def send_confirmation_email(request, user):
    """The email sent when someone asks for the link again, or changes their email address."""

    if not user.email:
        return False

    full_name = user.get_full_name().strip() or user.username
    link = confirm_email_url(request, user)
    paragraphs = [
        "Open the link below to confirm this is your email address for CulinaAI. It works for 3 days.",
        "If you didn't ask for this, you can ignore this email.",
    ]
    plain_message = "\n\n".join(
        [f"Hi {full_name},", paragraphs[0], link, paragraphs[1], "CulinaAI"]
    )
    html_message = build_branded_html("Confirm your email", paragraphs, "Confirm my email", link)

    return send_email(user.email, "Confirm your email for CulinaAI", plain_message, html_message, "confirmation")
