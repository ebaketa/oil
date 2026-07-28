"""Forms for configuring automated measurement tasks."""

from django import forms


class TaskBuilderForm(forms.Form):
    """Validate settings shared by every flexible automation task."""

    name = forms.CharField(max_length=120)
    interval_seconds = forms.FloatField(min_value=0.1, max_value=3600, initial=1)
    requested_samples = forms.IntegerField(
        min_value=1,
        max_value=10000,
        initial=10,
        label="Number of samples",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"
