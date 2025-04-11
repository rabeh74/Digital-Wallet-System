# wallet/notifications.py
from .tasks import send_transaction_notification as send_notification_task

class NotificationService:
    """Service for sending notifications"""
    def send_transaction_notification(self, email, transaction, message_type):
        """Send a notification about a transaction"""
        payload = {
            'amount' : abs(transaction.amount),
            'transaction_type' : transaction.transaction_type,
            'transaction_id' : transaction.id,
            'reference' : transaction.reference,
            'created_at' : transaction.created_at,
            'user' : transaction.wallet.user.email if transaction.wallet else None,
            'related_user' : transaction.related_wallet.user.email if transaction.related_wallet else None,
            'message_type' : message_type,
            'type' : transaction.transaction_type
        }
        send_notification_task.delay(email, payload)