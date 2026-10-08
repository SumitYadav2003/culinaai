"""
Creates sample cooking history for one user, so "learning from your cooking"
can be shown without cooking several meals first (for demos and testing).

    python manage.py seed_cooking_history --username demo
    python manage.py seed_cooking_history --username demo --recipe-id 12 --slower 1.4

It goes through the same code as real cooking mode (record_session), on one of
the user's saved recipes. The data is ordinary cooking history: the user can see
it, and delete it, under "Your cooking profile" on the dashboard.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from recipes.cooking_learning_service import build_cooking_tips, record_session, timer_adjustment
from recipes.cooking_mode_service import build_cooking_mode_context
from recipes.models import Recipe

NOTES = [
    ("technique", "Hard to tell when it was done"),
    ("technique", "It kept sticking to the pan"),
    ("unclear", "Not sure how small to chop"),
]


class Command(BaseCommand):
    help = "Create sample cooking-mode history for a user (demo data, deletable from the dashboard)."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)
        parser.add_argument("--recipe-id", type=int, help="A saved recipe of this user (default: the latest one).")
        parser.add_argument("--sessions", type=int, default=3)
        parser.add_argument("--slower", type=float, default=1.3, help="How much longer than the recipe the cook takes.")

    def handle(self, *args, **options):
        user = get_user_model().objects.filter(username=options["username"]).first()
        if not user:
            raise CommandError(f"No user called {options['username']!r}.")

        recipes = Recipe.objects.filter(user=user, is_saved=True).order_by("-created_at")
        recipe = recipes.filter(id=options["recipe_id"]).first() if options["recipe_id"] else recipes.first()
        if not recipe:
            raise CommandError("This user has no saved recipe to cook. Save one first, or pass --recipe-id.")

        steps = build_cooking_mode_context(recipe)["cooking_steps"]
        hands_on = [s["number"] for s in steps if s["kind"] != "waiting"] or [steps[0]["number"]]

        for session_number in range(options["sessions"]):
            payload = {"outcome": ["great", "ok", "great"][session_number % 3], "steps": []}
            for step in steps:
                item = {
                    "number": step["number"],
                    "seconds": round(step["timer_minutes"] * 60 * options["slower"]),
                    "completed": True,
                    "timer_used": step["timer_from_text"],
                    "went_fine": True,
                }
                payload["steps"].append(item)

            # The same two kinds of trouble come up more than once, as they would for a real cook.
            reason, note = NOTES[session_number % len(NOTES)]
            target = payload["steps"][[s["number"] for s in steps].index(hands_on[session_number % len(hands_on)])]
            target.update(trouble=reason, note=note, went_fine=False)

            if record_session(user, recipe, payload) is None:
                raise CommandError("Learning from cooking is off for this user. Turn it on in cooking mode first.")

        self.stdout.write(self.style.SUCCESS(
            f"Created {options['sessions']} cooking sessions of “{recipe.title}” for {user.username}."
        ))
        adjustment = timer_adjustment(user)
        tips = build_cooking_tips(user)
        self.stdout.write(
            f"Timers: {'hands-on steps ' + str(adjustment['percent']) + '% ' + ('longer' if adjustment['longer'] else 'shorter') if adjustment else 'not adjusted (not enough timed hands-on steps yet)'}."
        )
        self.stdout.write(f"New recipes: {', '.join(tips['reasons']) if tips else 'not adjusted yet'}.")
        self.stdout.write("Delete it any time: Dashboard > Your cooking profile > Delete my cooking history.")
