"""Forms for user-managed account settings."""

from django import forms
from django.contrib.auth import get_user_model

from .models import UserPreference


class ProfileForm(forms.ModelForm):
    """Edit account details and the user's interface theme."""

    theme = forms.ChoiceField(
        choices=UserPreference.Theme.choices,
        label="Colour theme",
    )
    show_top_navigation = forms.BooleanField(
        required=False,
        label="Show top navigation bar",
    )
    show_sidebar = forms.BooleanField(
        required=False,
        label="Show sidebar",
    )
    sidebar_position = forms.ChoiceField(
        choices=UserPreference.SidebarPosition.choices,
        label="Sidebar position",
        required=False,
    )

    class Meta:
        """Configure editable user fields."""

        model = get_user_model()
        fields = ("username", "first_name", "last_name", "email")

    def __init__(self, *args, **kwargs):
        """Apply Bootstrap styling to all profile fields."""
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"
        self.fields["theme"].widget.attrs["class"] = "form-select"
        self.fields["sidebar_position"].widget.attrs["class"] = "form-select"
        self.fields["show_top_navigation"].widget.attrs["class"] = (
            "form-check-input"
        )
        self.fields["show_sidebar"].widget.attrs["class"] = "form-check-input"

    def clean_username(self):
        """Reject usernames already used by another account."""
        username = self.cleaned_data["username"]
        existing_users = get_user_model().objects.filter(username__iexact=username)
        if self.instance.pk:
            existing_users = existing_users.exclude(pk=self.instance.pk)
        if existing_users.exists():
            raise forms.ValidationError("This username is already in use.")
        return username
