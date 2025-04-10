# wallet/apps.py
from django.apps import AppConfig


class WalletConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'wallet'

    def ready(self):
        # Import signals to register them when the app is ready
        import wallet.signals  # noqa