from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.core.cache import cache
from .models import Wallet, Transaction
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
        Wallet.objects.create(user=instance, phone_number=instance.phone_number)


@receiver(post_save, sender=Transaction)
def invalidate_transaction_cache(sender, instance, created, **kwargs):
    """
    Invalidate cache for transaction lists when a new transaction is created.
    
    Args:
        sender: The model class (Transaction).
        instance: The Transaction instance being saved.
        created: Boolean indicating if the instance was newly created.
        **kwargs: Additional keyword arguments.
    """
    if created:
        user_ids = []
        if instance.wallet and instance.wallet.user:
            user_ids.append(instance.wallet.user.id)
        if instance.related_wallet and instance.related_wallet.user:
            user_ids.append(instance.related_wallet.user.id)
        for user_id in user_ids:
            cache_key_pattern = f"transaction_list_{user_id}_*"
            cache.delete_pattern(cache_key_pattern)
