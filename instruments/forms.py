"""Forms for laboratory instrument inventory."""

from django import forms

from .models import Instrument


class InstrumentForm(forms.ModelForm):
    """Create or update an instrument inventory record."""

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
