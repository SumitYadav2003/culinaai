from django.test import TestCase
from django.contrib.auth.models import User


class BasicProjectTests(TestCase):
    def test_homepage_loads_successfully(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

    def test_user_can_be_created(self):
        user = User.objects.create_user(
            username="testuser",
            email="testuser@example.com",
            password="TestPassword123"
        )
        self.assertEqual(user.username, "testuser")
        self.assertTrue(user.check_password("TestPassword123"))

    def test_user_can_login(self):
        User.objects.create_user(
            username="testuser",
            email="testuser@example.com",
            password="TestPassword123"
        )

        login_successful = self.client.login(
            username="testuser",
            password="TestPassword123"
        )

        self.assertTrue(login_successful)