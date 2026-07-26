"""Views for the public OIL pages."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render

from .forms import ProfileForm
from .models import UserPreference


@login_required
def home(request):
    """Render the home page."""
    return render(request, "main/home.html")


@login_required
def contact(request):
    """Render the contact page."""
    return render(request, "main/contact.html")


@login_required
def about(request):
    """Render the about page."""
    return render(request, "main/about.html")


@login_required
def profile(request):
    """Display and update the current user's profile."""
    preference, _created = UserPreference.objects.get_or_create(user=request.user)

    if request.method == "POST":
        form = ProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            with transaction.atomic():
                form.save()
                preference.theme = form.cleaned_data["theme"]
                preference.save(update_fields=["theme"])
            messages.success(request, "Your profile has been updated.")
            return redirect("home")
    else:
        form = ProfileForm(
            instance=request.user,
            initial={"theme": preference.theme},
        )

    return render(request, "main/profile.html", {"form": form})
