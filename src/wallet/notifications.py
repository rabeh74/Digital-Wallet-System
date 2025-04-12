from .tasks import send_transaction_notification as send_notification_task
import os
from django.urls import reverse
from rest_framework_simplejwt.tokens import RefreshToken


class NotificationService:
    """Service for sending notifications"""
    def send_transaction_notification(self, email, transaction, message_type):
        """Send a notification about a transaction"""
        base_url = os.getenv('BASE_URL')
        token = self.generate_token(transaction.wallet.user)

        process_action_url = f"{base_url}{reverse('wallet:transaction-process-action')}"
        payload = {
            'amount' : abs(transaction.amount),
            'transaction_type' : transaction.transaction_type,
            'transaction_id' : transaction.id,
            'reference' : transaction.reference,
            'created_at' : transaction.created_at,
            'user' : transaction.wallet.user.email if transaction.wallet else None,
            'related_user' : transaction.related_wallet.user.email if transaction.related_wallet else None,
            'message_type' : message_type,
            'type' : transaction.transaction_type,
            'accept_url' : process_action_url,
            'reject_url' : process_action_url,
            'token' : token,
            'expiry_time' : transaction.expiry_time ,
        }
        send_notification_task.delay(email, payload)
    
    def generate_token(self, user):
        """Generate a JWT token for the user"""
        refresh = RefreshToken.for_user(user)
        return str(refresh.access_token)