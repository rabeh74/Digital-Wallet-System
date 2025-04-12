from celery import shared_task
from django.core.mail import send_mail
from django.template.loader import render_to_string
from .models import Transaction , Wallet
from django.utils import timezone
from datetime import timedelta
from django.db import transaction as db_transaction

@shared_task
def send_transaction_notification(user_email, payload ):
    """Send HTML email notification for a transaction"""
    try:
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
        
    except Exception as e:
        print(f"Failed to send email: {str(e)}")


@shared_task
def expire_old_transactions():
    """
    Celery task to expire pending transactions older than 24 hours.
    Updates their status to EXPIRED, refunds TRANSFER_OUT transactions, and logs the action.
    """
    EXPIRY_THRESHOLD_HOURS = 24
    expiry_threshold = timezone.now() - timedelta(hours=EXPIRY_THRESHOLD_HOURS)

    pending_transactions = Transaction.objects.filter(
        status=Transaction.Status.PENDING,
        created_at__lte=expiry_threshold
    ).select_related('wallet')  

    updated_count = 0

    try:
        with db_transaction.atomic():
            for pending_transaction in pending_transactions:
                pending_transaction.status = Transaction.Status.EXPIRED
                pending_transaction.updated_at = timezone.now()
                try:
                    pending_transaction.save()
                    updated_count += 1
                except Exception as e:
                    print(f"Failed to save transaction {pending_transaction.reference}: {str(e)}")
                    raise  

                # Refund logic for TRANSFER_OUT transactions
                if pending_transaction.transaction_type == Transaction.TransactionTypes.TRANSFER_OUT:
                    if pending_transaction.wallet is None:
                        print(f"Cannot refund transaction {pending_transaction.reference}: No wallet associated")
                        continue

                    # Lock wallet to prevent race conditions
                    try:
                        sender_wallet = Wallet.objects.select_for_update().get(id=pending_transaction.wallet.id)
                        refund_amount = abs(pending_transaction.amount)
                        sender_wallet.balance += refund_amount
                        sender_wallet.save()

                        # Verify the save
                        sender_wallet.refresh_from_db()
                        if sender_wallet.balance != (pending_transaction.wallet.balance + refund_amount):
                            print(f"Balance mismatch for wallet {sender_wallet.id}: expected {pending_transaction.wallet.balance + refund_amount}, got {sender_wallet.balance}")
                    except Exception as e:
                        print(f"Failed to refund transaction {pending_transaction.reference}: {str(e)}")
                        raise  

    except Exception as e:
        print(f"Transaction task failed: {str(e)}")
        raise

    if updated_count > 0:
        print(f"Expired {updated_count} pending transactions.")
    else:
        print("No pending transactions expired.")

    return updated_count