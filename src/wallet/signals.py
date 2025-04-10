# wallet/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from .models import Wallet

User = get_user_model()


@receiver(post_save, sender=User)
def create_user_wallet(sender, instance, created, **kwargs):
    """
    Signal handler to create a wallet for a user when their account is created.

    Args:
        sender: The model class (User).
        instance: The actual instance being saved (User instance).
        created: Boolean indicating if this is a new instance.
        **kwargs: Additional keyword arguments.
    """
    if created and not instance.is_staff:
        Wallet.objects.create(user=instance)