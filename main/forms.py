"""Forms for user-managed OIL profile settings."""

from django import forms
from django.contrib.auth import get_user_model

from .models import UserPreference


class ProfileForm(forms.ModelForm):
    """Edit account details and the user's interface theme."""

    theme = forms.ChoiceField(
        choices=UserPreference.Theme.choices,
        label="Colour theme",
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

    def clean_username(self):
        """Reject usernames already used by another account."""
        username = self.cleaned_data["username"]
        existing_users = get_user_model().objects.filter(username__iexact=username)

        if self.instance.pk:
            existing_users = existing_users.exclude(pk=self.instance.pk)

        if existing_users.exists():
            raise forms.ValidationError("This username is already in use.")

        return username
