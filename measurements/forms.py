"""Forms for measurement workflows."""

from django import forms

from instruments.models import Instrument

from .models import MeasurementRun


class MeasurementForm(forms.Form):
    """Select an instrument and the measurement it should perform."""

    instrument = forms.ModelChoiceField(
        queryset=Instrument.objects.none(),
    )
    measurement_type = forms.ChoiceField(
        choices=MeasurementRun.Function.choices,
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

    def clean(self):
        """Reject functions unsupported by the selected instrument driver."""
        cleaned_data = super().clean()
        instrument = cleaned_data.get("instrument")
        measurement_type = cleaned_data.get("measurement_type")

        if (
            instrument is not None
            and measurement_type
            and not instrument.supports_function(measurement_type)
        ):
            self.add_error(
                "measurement_type",
                "The selected instrument does not support this measurement.",
            )
        return cleaned_data


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
