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
    trigger_hours = forms.IntegerField(
        min_value=0,
        max_value=99,
        initial=0,
        required=False,
        label="HH",
    )
    trigger_minutes = forms.IntegerField(
        min_value=0,
        max_value=59,
        initial=0,
        required=False,
        label="MM",
    )
    trigger_seconds = forms.IntegerField(
        min_value=0,
        max_value=59,
        initial=1,
        required=False,
        label="SS",
    )
    trigger_hundredths = forms.IntegerField(
        min_value=0,
        max_value=99,
        initial=0,
        required=False,
        label="Hundredths",
    )
    interval_seconds = forms.FloatField(
        min_value=0.01,
        max_value=359999.99,
        required=False,
        widget=forms.HiddenInput,
    )
    start_delay_seconds = forms.FloatField(
        min_value=0,
        max_value=3600,
        initial=1,
        required=False,
        label="Start delay (seconds)",
    )
    requested_samples = forms.IntegerField(
        min_value=2,
        max_value=10000,
        initial=10,
        required=False,
        label="Number of measurements",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"
        self.fields["measurement_mode"].widget.attrs["class"] = "form-select"
        for name, label in (
            ("trigger_hours", "Hours"),
            ("trigger_minutes", "Minutes"),
            ("trigger_seconds", "Seconds"),
            ("trigger_hundredths", "Hundredths"),
        ):
            self.fields[name].widget.attrs["aria-label"] = label

    def clean(self):
        """Combine the trigger clock and validate mode-specific settings."""
        cleaned_data = super().clean()
        mode = cleaned_data.get("measurement_mode")
        if cleaned_data.get("start_delay_seconds") is None:
            cleaned_data["start_delay_seconds"] = 1
        trigger_parts = (
            cleaned_data.get("trigger_hours"),
            cleaned_data.get("trigger_minutes"),
            cleaned_data.get("trigger_seconds"),
            cleaned_data.get("trigger_hundredths"),
        )
        if all(part is None for part in trigger_parts):
            if cleaned_data.get("interval_seconds") is None:
                cleaned_data["interval_seconds"] = 1
        elif all(part is not None for part in trigger_parts):
            hours, minutes, seconds, hundredths = trigger_parts
            interval = hours * 3600 + minutes * 60 + seconds + hundredths / 100
            if interval <= 0:
                self.add_error(
                    "trigger_hundredths",
                    "Trigger period must be at least one hundredth of a second.",
                )
            else:
                cleaned_data["interval_seconds"] = interval
        else:
            self.add_error(
                "trigger_hundredths",
                "Enter all four parts of the trigger period.",
            )
        if mode == "loop":
            if cleaned_data.get("requested_samples") is None:
                self.add_error(
                    "requested_samples",
                    "Enter the number of measurements.",
                )
        else:
            cleaned_data["requested_samples"] = 1
        return cleaned_data
