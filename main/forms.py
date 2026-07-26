"""Forms for user-managed OIL profile settings."""

from django import forms
from django.contrib.auth import get_user_model
from django.db.models import TextChoices

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


class MeasurementForm(forms.Form):
    """Select an instrument and the measurement it should perform."""

    class Type(TextChoices):
        """Measurement operations currently supported by every driver."""

        DC_VOLTAGE = "dc_voltage", "DC voltage"

    instrument = forms.ModelChoiceField(
        queryset=Instrument.objects.none(),
    )
    measurement_type = forms.ChoiceField(
        choices=Type.choices,
        label="Measurement",
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, **kwargs):
        """Load current instruments and apply Bootstrap field styling."""
        super().__init__(*args, **kwargs)
        self.fields["instrument"].queryset = Instrument.objects.all()

        for field in self.fields.values():
            css_class = "form-select" if isinstance(
                field.widget,
                forms.Select,
            ) else "form-control"
            field.widget.attrs["class"] = css_class

class LoopMeasurementForm(MeasurementForm):
    """Configure a finite sequence of measurements."""

    field_order = (
        "instrument",
        "measurement_type",
        "count",
        "interval_seconds",
        "notes",
    )

    count = forms.IntegerField(
        min_value=2,
        max_value=100,
        initial=10,
        label="Number of measurements",
    )
    interval_seconds = forms.FloatField(
        min_value=0.1,
        max_value=3600,
        initial=1,
        label="Interval (seconds)",
    )

    def __init__(self, *args, **kwargs):
        """Apply the loop-specific function label."""
        super().__init__(*args, **kwargs)
        self.fields["measurement_type"].label = "Measurement (Function)"


class ContinuousMeasurementForm(MeasurementForm):
    """Configure measurements that continue until explicitly stopped."""

    field_order = (
        "instrument",
        "measurement_type",
        "interval_seconds",
        "notes",
    )

    interval_seconds = forms.FloatField(
        min_value=0.1,
        max_value=3600,
        initial=1,
        label="Interval (seconds)",
    )

    def __init__(self, *args, **kwargs):
        """Apply the continuous-measurement function label."""
        super().__init__(*args, **kwargs)
        self.fields["measurement_type"].label = "Measurement (Function)"
