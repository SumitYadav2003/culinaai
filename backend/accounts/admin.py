from django.contrib import admin

from .models import UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "email_confirmed", "weekly_email", "is_demo", "created_at")
    list_filter = ("email_confirmed", "weekly_email", "is_demo")
    search_fields = ("user__username", "user__email")
