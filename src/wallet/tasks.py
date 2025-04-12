from celery import shared_task
from django.core.mail import send_mail
from django.template.loader import render_to_string
from .models import Transaction , Wallet
from django.utils import timezone
from datetime import timedelta
from django.db import transaction as db_transaction
import logging
from .utils import set_logging_context

logger = logging.getLogger('wallet.tasks')

@shared_task
def send_transaction_notification(user_email, payload ):
    """Send HTML email notification for a transaction"""
    try:
        set_logging_context(
            transaction_ref=payload['reference'],
            amount=payload['amount'],
        )
        message_type = payload['message_type']
        template_name = f"emails/{message_type}.html"
        html_content = render_to_string(template_name, payload)
        subject = html_content.split('<title>')[1].split('</title>')[0].strip() if '<title>' in html_content else f"Transaction Update {payload['transaction_id']}"

        recipient_list = [user_email]
        send_mail(
            subject=subject,
            html_message=html_content,
            from_email='no-reply@purplewallet.com',
            recipient_list=recipient_list,
            fail_silently=False,
            message = None
        )
        
        logger.info(f"Email sent to {user_email} for transaction {payload['transaction_id']}")
        
    except Exception as e:
        logger.error(f"Failed to send email: {str(e)}")


@shared_task
def expire_old_transactions():
    """
    Celery task to expire pending transactions older than 24 hours.
    Updates their status to EXPIRED, refunds CREDIT transactions, and logs the action.
    """
    EXPIRY_THRESHOLD_HOURS = 24
    expiry_threshold = timezone.now() - timedelta(hours=EXPIRY_THRESHOLD_HOURS)

    # Filter transactions older than 24 hours
    pending_transactions = Transaction.objects.filter(
        status=Transaction.Status.PENDING,
        created_at__lte=expiry_threshold
    ).select_related('wallet')  # Optimize by fetching wallet

    updated_count = 0

    try:
        with db_transaction.atomic():
            for pending_transaction in pending_transactions:
                # Update transaction status
                set_logging_context(
                    user_id=pending_transaction.wallet.user.id if pending_transaction.wallet else None,
                    transaction_ref=pending_transaction.reference,
                    wallet_id=pending_transaction.wallet.id if pending_transaction.wallet else None
                )
                pending_transaction.status = Transaction.Status.EXPIRED
                pending_transaction.updated_at = timezone.now()
                try:
                    pending_transaction.save()
                    updated_count += 1
                except Exception as e:
                    logger.error(f"Failed to save transaction {pending_transaction.reference}: {str(e)}")
                    raise  # Rollback if transaction save fails

                # Refund logic for CREDIT transactions
                if pending_transaction.transaction_type == Transaction.TransactionTypes.CREDIT:
                    if pending_transaction.wallet is None:
                        logger.error(f"Cannot refund transaction {pending_transaction.reference}: No wallet associated")
                        continue

                    # Lock wallet to prevent race conditions
                    try:
                        sender_wallet = Wallet.objects.select_for_update().get(id=pending_transaction.wallet.id)
                        logger.info(f"Refunding {pending_transaction.amount} to {sender_wallet.user.email}")
                        logger.info(f"Wallet before: {sender_wallet.balance}")

                        refund_amount = abs(pending_transaction.amount)
                        sender_wallet.balance += refund_amount
                        sender_wallet.save()

                        # Verify the save
                        sender_wallet.refresh_from_db()
                        logger.info(f"Wallet after: {sender_wallet.balance}")
                        if sender_wallet.balance != (pending_transaction.wallet.balance + refund_amount):
                            logger.error(f"Balance mismatch for wallet {sender_wallet.id}: expected {pending_transaction.wallet.balance + refund_amount}, got {sender_wallet.balance}")
                    except Exception as e:
                        logger.error(f"Failed to refund transaction {pending_transaction.reference}: {str(e)}")
                        raise  # Rollback if refund fails

    except Exception as e:
        logger.error(f"Transaction task failed: {str(e)}")
        raise

    if updated_count > 0:
        logger.info(f"Expired {updated_count} pending transactions.")
    else:
        logger.info("No pending transactions expired.")

    return updated_count