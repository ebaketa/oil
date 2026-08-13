"""Template context processors for account preferences."""

from .models import UserPreference


def user_theme(request):
    """Expose the current user's theme and available themes to templates."""
    theme = UserPreference.Theme.LIGHT
    show_top_navigation = True
    show_sidebar = True
    sidebar_position = UserPreference.SidebarPosition.LEFT

    if request.user.is_authenticated:
        preference = (
            UserPreference.objects.filter(user=request.user)
            .values(
                "theme",
                "show_top_navigation",
                "show_sidebar",
                "sidebar_position",
            )
            .first()
        )
        if preference:
            theme = preference["theme"]
            show_top_navigation = preference["show_top_navigation"]
            show_sidebar = preference["show_sidebar"]
            sidebar_position = preference["sidebar_position"]

    return {
        "oil_theme": theme,
        "oil_show_top_navigation": show_top_navigation,
        "oil_show_sidebar": show_sidebar,
        "oil_sidebar_position": sidebar_position,
    }
