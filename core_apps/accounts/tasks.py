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

from core_apps.accounts.emails import send_suspicious_activity_alert
from .models import BankAccount, Transaction
from django.contrib.auth import get_user_model
from django.db.models import Q, Sum
from reportlab.lib.units import inch
from django.db import transaction as db_transaction
from os import getenv
from decimal import Decimal
from datetime import timedelta
from django.utils import timezone

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

        buffer = BytesIO()

        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(letter),
            rightMargin=30,
            leftMargin=30,
            topMargin=30,
            bottomMargin=18,
        )

        elements = []
        styles = getSampleStyleSheet()

        elements.append(
            Paragraph(
                f"Transaction History for {user.get_full_name()} ({user.email})",
                styles["Title"],
            )
        )
        elements.append(Spacer(1, 12))

        data = [
            ["Date", "Type", "Amount", "Description", "Status", "Sender", "Receiver"]
        ]

        for transaction in transactions:
            data.append(
                [
                    transaction.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    transaction.get_transaction_type_display(),
                    f"${transaction.amount:.2f}",
                    (
                        transaction.description[:30] + "..."
                        if len(transaction.description) > 30
                        else transaction.description
                    ),
                    transaction.get_status_display(),
                    transaction.sender.get_full_name() if transaction.sender else "N/A",
                    (
                        transaction.receiver.get_full_name()
                        if transaction.receiver
                        else "N/A"
                    ),
                ]
            )

        col_widths = [
            1.8 * inch,
            0.8 * inch,
            1.2 * inch,
            2.5 * inch,
            0.8 * inch,
            1.2 * inch,
            1.2 * inch,
        ]

        table = Table(data, colWidths=col_widths)

        styles = TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
                ("GRID", (0, 0), (-1, -1), 1, colors.black),
                ("TEXTCOLOR", (0, 1), (-1, -1), colors.black),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
                ("WORDWRAP", (0, 0), (-1, -1), True),
                ("FONTSIZE", (0, 1), (-1, -1), 10),
                ("TOPADDING", (0, 1), (-1, -1), 6),
            ]
        )

        table.setStyle(styles)
        elements.append(table)
        doc.build(elements)

        # move the buffer position to the beginning
        buffer.seek(0)
        pdf = buffer.getvalue()
        buffer.close()

        subject = _("Your Transaction History PDF")
        message = _(
            f"Dear {user.full_name}, Please find attached your transaction history PDF."
        )
        from_email = settings.DEFAULT_FROM_EMAIL
        recipient_list = [user.email]
        email = EmailMessage(subject, message, from_email, recipient_list)
        email.attach(
            f"transaction_{start_date}_to_{end_date}.pdf", pdf, "application/pdf"
        )

        try:
            email.send()
            logger.info(f"Transaction PDF sent successfully to user {user_id}")
            return f"Transaction PDF sent successfully to user {user_id}"
        except Exception as e:
            logger.error(
                f"Error sending transaction PDF email to user {user_id}: {str(e)}"
            )

    except Exception as e:
        logger.error(f"Error generating transaction PDF for user {user_id}: {str(e)}")
        return


@shared_task
def apply_daily_interest():
    savings_accounts = BankAccount.objects.filter(
        account_type=BankAccount.AccountType.SAVINGS
    )
    for account in savings_accounts:
        try:
            with db_transaction.atomic():
                account.apply_daily_interest()
                logger.info(
                    f"Daily interest applied for account {account.account_number}"
                )
        except Exception as e:
            logger.error(
                f"Error applying daily interest for account {account.account_number}: {str(e)}"
            )

    logger.info(
        f"Daily interest application task completed for {savings_accounts.count()} savings accounts."
    )

    return f"Daily interest application task completed for {savings_accounts.count()} savings accounts."


@shared_task
def detect_suspicious_activities():
    LARGE_TRANSACTION_THRESHOLD = Decimal(getenv("LARGE_TRANSACTION_THRESHOLD"))

    FREQUENT_TRANSACTION_THRESHOLD = int(getenv("FREQUENT_TRANSACTION_THRESHOLD"))

    TIME_WINDOW_HOURS = int(getenv("TIME_WINDOW_HOURS"))

    TIME_WINDOW = timedelta(hours=TIME_WINDOW_HOURS)

    now = timezone.now()

    time_threshold = now - TIME_WINDOW

    suspicious_activities = []

    large_transactions = Transaction.objects.filter(
        amount__gte=LARGE_TRANSACTION_THRESHOLD, created_at__lte=time_threshold
    )

    for transaction in large_transactions:
        suspicious_activities.append(
            f"Large transaction detected: {transaction.amount} by user {transaction.user.email}"
        )

    users = User.objects.all()
    for user in users:
        transaction_count = Transaction.objects.filter(
            user=user, created_at__gte=time_threshold
        ).count()

        if transaction_count >= FREQUENT_TRANSACTION_THRESHOLD:
            suspicious_activities.append(
                f"Frequent transactions detected: {transaction_count} by user {user.email}"
            )

    accounts = BankAccount.objects.all()

    for account in accounts:
        balance_change = Transaction.objects.filter(
            Q(sender_account=account) | Q(receiver_account=account),
            created_at__gte=time_threshold,
        ).aggregate(
            total_sent=Sum("amount", filter=Q(sender_account=account)),
            total_received=Sum("amount", filter=Q(receiver_account=account)),
        )
        total_change = (balance_change["total_received"] or Decimal("0")) - (
            balance_change["total_sent"] or Decimal("0")
        )

        if abs(total_change) > LARGE_TRANSACTION_THRESHOLD:
            suspicious_activities.append(
                f"Large balance change detected: {total_change} by user {account.account_number}"
            )

        if suspicious_activities:
            num_activities = send_suspicious_activity_alert(suspicious_activities)
            if num_activities > 0:
                return (
                    f"Suspicious activity check completed. {num_activities} suspicious "
                    f"activities detected and reported "
                )
            else:
                return (
                    f"Suspicious activity check completed. Activities "
                    f"detected but alert email failed to send "
                )
    return "Suspicious activity check completed. No suspicious activities detected"
