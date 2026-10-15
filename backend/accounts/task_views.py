"""
/tasks/weekly/: the weekly job, called by GitHub Actions (.github/workflows/weekly-email.yml)
because Render's free plan has no scheduled jobs. It sends the Sunday emails and
deletes old demo accounts.

It only runs with the right secret: "Authorization: Bearer <CRON_SECRET>".
When CRON_SECRET isn't set, the address doesn't exist (404).
"""

import hmac
import logging

from django.conf import settings
from django.http import Http404, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from recipes.demo_service import delete_old_demo_users
from recipes.weekly_email_service import send_weekly_emails

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def weekly_tasks_view(request):
    secret = settings.CRON_SECRET
    if not secret:
        raise Http404()

    given = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(given.encode(), secret.encode()):
        return JsonResponse({"error": "not allowed"}, status=403)

    emails = send_weekly_emails(base_url=request.build_absolute_uri("/").rstrip("/"))
    demos_deleted = delete_old_demo_users()
    result = {"emails": emails, "demo_accounts_deleted": demos_deleted}
    logger.info("Weekly tasks: %s", result)
    return JsonResponse(result)
