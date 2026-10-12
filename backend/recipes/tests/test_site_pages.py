"""
Log in, sign up, password reset, profile, About, the impact page and the
error pages after the redesign.
"""

from django.contrib.auth.models import User
from django.core import mail
from django.template.loader import render_to_string
from django.test import Client, TestCase, override_settings
from django.urls import reverse


class SignInPagesTests(TestCase):
    def test_sign_up_then_log_in(self):
        html = self.client.get(reverse("signup")).content.decode()
        self.assertIn("Create an account", html)
        self.assertNotIn("Sumit Yadav", html)

        response = self.client.post(reverse("signup"), {
            "full_name": "Alex Morgan", "email": "alex@example.com",
            "password1": "Tomato-soup-42", "password2": "Tomato-soup-42",
        }, follow=True)
        html = response.content.decode()
        self.assertIn("Your account is ready.", html)
        self.assertIn("Log in to start cooking.", html)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Welcome, Alex Morgan", mail.outbox[0].alternatives[0][0])

        response = self.client.post(reverse("login"), {"username": "alex@example.com", "password": "wrong-one"})
        self.assertContains(response, "That email and password don&#x27;t match.")
        response = self.client.post(reverse("login"), {"username": "alex@example.com", "password": "Tomato-soup-42"})
        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)

    def test_unknown_email_is_explained(self):
        response = self.client.post(reverse("login"), {"username": "nobody@example.com", "password": "x"})
        self.assertContains(response, "There&#x27;s no account with that email.")

    def test_password_reset_pages(self):
        User.objects.create_user("cook", "cook@example.com", "pass-12345")
        response = self.client.post(reverse("password_reset"), {"email": "cook@example.com"}, follow=True)
        self.assertContains(response, "Check your email")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Choose a new password", mail.outbox[0].alternatives[0][0])
        html = self.client.get(reverse("password_reset_confirm", args=["xx", "yy"])).content.decode()
        self.assertIn("This link has expired", html)


class ProfileAndInfoPagesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("cook", "cook@example.com", "pass-12345")

    def test_profile_saves_details_and_changes_password(self):
        self.client.force_login(self.user)
        html = self.client.get(reverse("profile_summary")).content.decode()
        self.assertIn("Your details", html)
        self.assertNotIn("Django hashing", html)

        response = self.client.post(reverse("profile_summary"), {
            "form_type": "profile_update", "first_name": "Sam", "last_name": "Lee",
            "username": "cook", "email": "cook@example.com", "bio": "",
        }, follow=True)
        self.assertContains(response, "Saved your details.")

        response = self.client.post(reverse("profile_summary"), {
            "form_type": "password_change", "old_password": "pass-12345",
            "new_password1": "Lentil-stew-77", "new_password2": "Lentil-stew-77",
        }, follow=True)
        self.assertContains(response, "Password changed.")

    def test_about_page_is_plain(self):
        html = self.client.get(reverse("about_culinaai")).content.decode()
        self.assertIn("What it can't do", html)
        self.assertNotIn("robot", html.lower())


class ErrorPagesTests(TestCase):
    def test_page_not_found(self):
        response = self.client.get("/no-such-page/")
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "We couldn't find that page", status_code=404)

    def test_expired_form(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post(reverse("login"), {"username": "a@example.com", "password": "x"})
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "That didn't go through", status_code=403)

    def test_server_error_page_renders_on_its_own(self):
        html = render_to_string("500.html")
        self.assertIn("Something went wrong on our side", html)
