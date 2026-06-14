from django.contrib import admin
from django.shortcuts import render
from django.urls import include, path


def home_view(request):
    return render(request, "pages/home.html")


urlpatterns = [
    path("admin/", admin.site.urls),
    path("", home_view, name="home"),
    path("", include("accounts.urls")),
    path("dashboard/", include("dashboard.urls")),
    path("recipes/", include("recipes.urls")),
]