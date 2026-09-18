"""Persistent ownership for interactive instrument panels."""

from django.conf import settings
from django.db import models

from main.models import Instrument


class PanelLease(models.Model):
    """Give one browser panel exclusive control of an instrument."""

    instrument = models.OneToOneField(
        Instrument,
        on_delete=models.CASCADE,
        related_name="panel_lease",
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    owner_token = models.CharField(max_length=64)
    last_seen = models.DateTimeField()
    latest_status = models.JSONField(default=dict, blank=True)

