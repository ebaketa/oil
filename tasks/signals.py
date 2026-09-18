"""Keep cached task counters synchronized with stored samples."""

from django.db.models import F
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from .models import AutomationTask, TaskSample


def _is_counted(status):
    return status != TaskSample.Status.ACQUIRING


@receiver(pre_save, sender=TaskSample)
def remember_previous_sample_status(sender, instance, **kwargs):
    """Remember whether an existing sample was included in the counter."""
    if not instance.pk:
        instance._was_counted = False
        return
    previous = sender.objects.filter(pk=instance.pk).values_list(
        "status",
        flat=True,
    ).first()
    instance._was_counted = previous is not None and _is_counted(previous)


@receiver(post_save, sender=TaskSample)
def update_sample_count_after_save(sender, instance, **kwargs):
    """Adjust the cached count when a sample enters or leaves a final state."""
    was_counted = getattr(instance, "_was_counted", False)
    is_counted = _is_counted(instance.status)
    delta = int(is_counted) - int(was_counted)
    if delta:
        AutomationTask.objects.filter(pk=instance.task_id).update(
            sample_count=F("sample_count") + delta,
        )


@receiver(post_delete, sender=TaskSample)
def update_sample_count_after_delete(sender, instance, **kwargs):
    """Remove a deleted completed or failed sample from the cached count."""
    if _is_counted(instance.status):
        AutomationTask.objects.filter(
            pk=instance.task_id,
            sample_count__gt=0,
        ).update(sample_count=F("sample_count") - 1)
