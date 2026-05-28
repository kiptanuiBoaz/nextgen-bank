from io import BytesIO
from celery import shared_task
from dateutil import parser
import django
from django.conf import settings
from django.core.mail import EmailMessage
from django.utils.translation import gettext_lazy as _
from loguru import logger
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from .models import BankAccount, Transaction
from django.contrib.auth import get_user_model
from django.db.models import Q

User = get_user_model()


@shared_task
def generate_transaction_pdf(user_id, start_date, end_date, account_number=None):
    try:
        user = User.objects.get(id=user_id)
        # parse the start and end dates from string to date objects
        start_date = parser.parse(start_date).date()
        end_date = parser.parse(end_date).date()

        transactions = Transaction.objects.filter(
            Q(sender=user) | Q(receiver=user),
            created_at__date__range=[start_date, end_date],
        )

        if account_number:
            account = BankAccount.objects.get(account_number=account_number, user=user)
            transactions = transactions.filter(
                Q(sender_account=account) | Q(receiver_account=account)
            )

    except Exception as e:
        logger.error(f"Error generating transaction PDF for user {user_id}: {str(e)}")
        return
