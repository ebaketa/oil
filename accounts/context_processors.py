"""Template context processors for account preferences."""

from .models import UserPreference


def user_theme(request):
    """Expose the current user's theme and available themes to templates."""
    theme = UserPreference.Theme.BLUE

    if request.user.is_authenticated:
        theme = (
            UserPreference.objects.filter(user=request.user)
            .values_list("theme", flat=True)
            .first()
            or UserPreference.Theme.BLUE
        )

    return {
        "oil_theme": theme,
    }
