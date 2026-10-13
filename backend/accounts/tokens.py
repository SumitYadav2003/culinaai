from django.contrib.auth.tokens import PasswordResetTokenGenerator


class EmailConfirmTokenGenerator(PasswordResetTokenGenerator):
    """
    Makes the link in the "confirm your email" email. The link stops working once
    the email is confirmed, if the email address changes, or after
    PASSWORD_RESET_TIMEOUT (three days by default).
    """

    key_salt = "culinaai.accounts.EmailConfirmTokenGenerator"

    def _make_hash_value(self, user, timestamp):
        confirmed = getattr(getattr(user, "profile", None), "email_confirmed", False)
        return f"{user.pk}{user.email}{confirmed}{timestamp}"


email_confirm_token = EmailConfirmTokenGenerator()
