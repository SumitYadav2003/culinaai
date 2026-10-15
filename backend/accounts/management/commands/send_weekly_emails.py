from django.core.management.base import BaseCommand

from recipes.demo_service import delete_old_demo_users
from recipes.weekly_email_service import send_weekly_emails


class Command(BaseCommand):
    help = "Send the Sunday emails that are due and delete old demo accounts (the same job as /tasks/weekly/)."

    def handle(self, *args, **options):
        counts = send_weekly_emails()
        deleted = delete_old_demo_users()
        self.stdout.write(
            f"Sunday emails: {counts['sent']} sent, {counts['nothing_to_say']} had nothing to say, "
            f"{counts['failed']} failed. Old demo accounts deleted: {deleted}."
        )
