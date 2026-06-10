from django.contrib.auth import login
from django.contrib import messages
from django.shortcuts import redirect, render

from .forms import SignUpForm


def signup_view(request):
    if request.method == "POST":
        form = SignUpForm(request.POST)

        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Your CulinaAI account has been created successfully.")
            return redirect("dashboard")

        messages.error(request, "Please correct the errors below.")
    else:
        form = SignUpForm()

    return render(request, "accounts/signup.html", {"form": form})