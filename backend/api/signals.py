# backend/api/signals.py
from django.contrib.auth.models import Group
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import WIGOSNodeGroup

@receiver(post_save, sender=Group)
def create_or_update_group_profile(sender, instance, created, **kwargs):
    if created:
        WIGOSNodeGroup.objects.create(group=instance)
    else:
        # Safeguard for existing groups that don't have a profile yet
        WIGOSNodeGroup.objects.get_or_create(group=instance)
