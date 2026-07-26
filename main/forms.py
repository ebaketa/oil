"""Forms for user-managed OIL profile settings."""

from django import forms
from django.contrib.auth import get_user_model

from .models import Instrument, UserPreference


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


class InstrumentForm(forms.ModelForm):
    """Create an instrument inventory record."""

    class Meta:
        """Configure editable instrument fields."""

        model = Instrument
        fields = (
            "name",
            "manufacturer",
            "model_name",
            "serial_number",
            "driver",
            "address",
            "description",
        )
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        """Apply Bootstrap styling to instrument fields."""
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css_class = "form-select" if isinstance(
                field.widget,
                forms.Select,
            ) else "form-control"
            field.widget.attrs["class"] = css_class
