from django.conf import settings
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


class UserProfile(models.Model):
    """
    Stores extra profile information for each CulinaAI user.

    We keep this separate from Django's default User model so the project
    remains safe and simple without changing the authentication system.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )

    profile_image = models.ImageField(
        upload_to="profile_images/",
        null=True,
        blank=True,
        help_text="User profile image uploaded from the profile page.",
    )

    bio = models.TextField(
        blank=True,
        help_text="Optional short user bio for future profile improvements.",
    )

    # True for everyone except people who signed up and haven't opened the link
    # in their confirmation email yet (the signup form sets it to False).
    email_confirmed = models.BooleanField(default=True)

    # Saved once on the profile and filled in on every New recipe form, so people
    # don't have to type their allergies each time. They can still change them for one recipe.
    diet_preferences = models.ManyToManyField("recipes.DietPreference", blank=True, related_name="profiles")
    other_diet = models.CharField(max_length=200, blank=True)
    allergies = models.TextField(blank=True)

    # A temporary account made by "Try the demo". Deleted after a day, or on logging out.
    is_demo = models.BooleanField(default=False)

    # The Sunday email: what in the pantry goes off soon and what's planned next week.
    weekly_email = models.BooleanField(default=False)
    weekly_email_sent_on = models.DateField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"

    def __str__(self):
        return f"{self.user.username} Profile"

    @property
    def has_diet_settings(self):
        return bool(self.allergies.strip() or self.other_diet.strip() or self.diet_preferences.exists())


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    """
    Automatically creates a UserProfile whenever a new user is created.
    Also ensures existing users get a profile safely.
    """

    if created:
        UserProfile.objects.create(user=instance)
    else:
        UserProfile.objects.get_or_create(user=instance)