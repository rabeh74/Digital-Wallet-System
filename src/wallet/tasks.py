# wallet/tasks.py
from celery import shared_task
from django.core.mail import send_mail
from django.template.loader import render_to_string
from .models import Transaction
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

# wallet/tasks.py
@shared_task
def expire_old_transactions():
    """
    Celery task to expire pending transactions older than 24 hours.
    Updates their status to EXPIRED and logs the action.
    """
    EXPIRY_THRESHOLD_HOURS = 24
    expiry_threshold = timezone.now() - timedelta(hours=EXPIRY_THRESHOLD_HOURS)

    pending_transactions = Transaction.objects.filter(
        status=Transaction.Status.PENDING,
        created_at__lte=expiry_threshold
    )

    with db_transaction.atomic():
        updated_count = pending_transactions.update(
            status=Transaction.Status.EXPIRED,
            updated_at=timezone.now()
        )

    if updated_count > 0:
        print(f"Expired {updated_count} pending transactions.")
    return updated_count