from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from .views import login_view, logout_view, profile_summary_view, signup_view


urlpatterns = [
    path("signup/", signup_view, name="signup"),
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),

    # Profile Summary
    # Professional account summary page for authenticated users.
    path("profile/", profile_summary_view, name="profile_summary"),

    # Password Reset - Step 1
    # User enters their email address.
    #
    # Deployment-ready email setup:
    # - email_template_name gives a plain text fallback email.
    # - html_email_template_name gives a branded HTML email.
    # - The reset link will use localhost during local testing.
    # - The reset link will use your real domain after AWS deployment.
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(
            template_name="accounts/password_reset.html",
            email_template_name="accounts/password_reset_email.txt",
            html_email_template_name="accounts/password_reset_email.html",
            subject_template_name="accounts/password_reset_subject.txt",
            success_url=reverse_lazy("password_reset_done"),
        ),
        name="password_reset",
    ),

    # Password Reset - Step 2
    # User sees this page after submitting their email.
    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="accounts/password_reset_done.html",
        ),
        name="password_reset_done",
    ),

    # Password Reset - Step 3
    # User opens the secure reset link from their email.
    path(
        "reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="accounts/password_reset_confirm.html",
            success_url=reverse_lazy("password_reset_complete"),
        ),
        name="password_reset_confirm",
    ),

    # Password Reset - Step 4
    # User sees this page after setting a new password.
    path(
        "reset/done/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="accounts/password_reset_complete.html",
        ),
        name="password_reset_complete",
    ),
]