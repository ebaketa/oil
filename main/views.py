"""Views for the public OIL pages."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render

from .forms import InstrumentForm, ProfileForm
from .models import Instrument, UserPreference


@login_required
def dashboard(request):
    """Render the dashboard page."""
    instruments = Instrument.objects.all()
    return render(
        request,
        "main/dashboard.html",
        {
            "instruments": instruments,
            "instrument_count": instruments.count(),
            "online_instrument_count": instruments.filter(
                status=Instrument.Status.ONLINE,
            ).count(),
        },
    )


@login_required
def instrument_list(request):
    """Display the laboratory instrument inventory."""
    instruments = Instrument.objects.all()
    return render(
        request,
        "main/instrument_list.html",
        {
            "instruments": instruments,
            "instrument_count": instruments.count(),
        },
    )


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
            return redirect("dashboard")
    else:
        form = ProfileForm(
            instance=request.user,
            initial={"theme": preference.theme},
        )

    return render(request, "main/profile.html", {"form": form})


@login_required
def instrument_create(request):
    """Display and process the new-instrument form."""
    if request.method == "POST":
        form = InstrumentForm(request.POST)
        if form.is_valid():
            instrument = form.save()
            messages.success(request, f"{instrument.name} has been added.")
            return redirect("instrument_list")
    else:
        form = InstrumentForm()

    return render(request, "main/instrument_form.html", {"form": form})
