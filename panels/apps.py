from django.apps import AppConfig


class PanelsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "panels"
    # Keep the existing migration/table namespace when upgrading from the
    # former dmm_panel package.
    label = "dmm_panel"
    verbose_name = "DMM Front Panel"
