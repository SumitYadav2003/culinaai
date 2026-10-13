from django.utils.functional import SimpleLazyObject


def account_status(request):
    """
    Two things the page layout needs about the signed-in user. Both are lazy, so
    the database is only asked when a page actually shows them.

    email_unconfirmed: show the "confirm your email" bar at the top.
    ai_allowance: how many AI recipe actions are left today.
    """

    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {}

    from accounts.confirmation import needs_email_confirmation
    from recipes.ai_limits import allowance

    return {
        "email_unconfirmed": SimpleLazyObject(lambda: needs_email_confirmation(user)),
        "ai_allowance": SimpleLazyObject(lambda: allowance(user, "recipe")),
    }
