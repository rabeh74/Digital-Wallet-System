# wallet/tasks.py
from email import message
from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from .models import Transaction

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