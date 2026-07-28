"""Views for account profiles."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render

from .forms import ProfileForm
from .models import UserPreference


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
                preference.show_top_navigation = form.cleaned_data[
                    "show_top_navigation"
                ]
                preference.show_sidebar = form.cleaned_data["show_sidebar"]
                preference.sidebar_position = (
                    form.cleaned_data["sidebar_position"]
                    or preference.sidebar_position
                )
                preference.save(
                    update_fields=(
                        "theme",
                        "show_top_navigation",
                        "show_sidebar",
                        "sidebar_position",
                    ),
                )
            messages.success(request, "Your profile has been updated.")
            return redirect("dashboard")
    else:
        form = ProfileForm(
            instance=request.user,
            initial={
                "theme": preference.theme,
                "show_top_navigation": preference.show_top_navigation,
                "show_sidebar": preference.show_sidebar,
                "sidebar_position": preference.sidebar_position,
            },
        )

    return render(request, "main/profile.html", {"form": form})
