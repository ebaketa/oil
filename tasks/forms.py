"""Forms for configuring automated measurement tasks."""

from django import forms


class TaskBuilderForm(forms.Form):
    """Validate settings shared by every flexible automation task."""

    name = forms.CharField(max_length=120, label="Task name")
    description = forms.CharField(
        max_length=500,
        required=False,
        label="Short description",
        widget=forms.Textarea(
            attrs={
                "rows": 2,
                "placeholder": "Briefly describe the purpose of this task",
            },
        ),
    )
    measurement_mode = forms.ChoiceField(
        choices=(
            ("single", "Single"),
            ("continuous", "Continuous"),
            ("loop", "Loop"),
        ),
        initial="single",
        label="Measurement type",
    )
    interval_seconds = forms.FloatField(
        min_value=0.1,
        max_value=3600,
        initial=1,
        required=False,
        label="Interval (seconds)",
    )
    requested_samples = forms.IntegerField(
        min_value=2,
        max_value=100,
        initial=10,
        required=False,
        label="Number of measurements",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"
        self.fields["measurement_mode"].widget.attrs["class"] = "form-select"

    def clean(self):
        """Require timing fields only for the modes that use them."""
        cleaned_data = super().clean()
        mode = cleaned_data.get("measurement_mode")
        if mode in {"continuous", "loop"}:
            if cleaned_data.get("interval_seconds") is None:
                self.add_error(
                    "interval_seconds",
                    "Enter the measurement interval.",
                )
        else:
            cleaned_data["interval_seconds"] = 1
        if mode == "loop":
            if cleaned_data.get("requested_samples") is None:
                self.add_error(
                    "requested_samples",
                    "Enter the number of measurements.",
                )
        else:
            cleaned_data["requested_samples"] = 1
        return cleaned_data
