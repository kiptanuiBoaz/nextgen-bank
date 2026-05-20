import base64
from io import BytesIO

from celery import shared_task
from dateutil import parser
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMessage
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from loguru import logger
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

# from .models import BankAccount, Transaction
from django.db import transaction
from os import getenv
from decimal import Decimal
from datetime import timedelta
from django.utils import timezone
from django.db.models import Q, Sum

# from .emails import send_suspicious_activity_alert
from uuid import UUID
import base64
import cloudinary.uploader
from django.apps import apps
from django.core.files.storage import default_storage


@shared_task(name="upload_photos_to_cloudinary")
def upload_photos_to_cloudinary(profile_id: UUID, photos: dict) -> None:
    try:
        profile_modle = apps.get_model("user_profile", "Profile")
        profile = profile_modle.objects.get(id=profile_id)

        for field_name, photo_data in photos.items():
            if photo_data["type"] == "base64":
                image_content = base64.b64decode(photo_data["data"])
                response = cloudinary.uploader.upload(image_content)

            else:
                # open the file in read mode
                with open(photo_data["data"], "rb") as image_file:
                    response = cloudinary.uploader.upload(image_file)
                default_storage.delete(photo_data["path"])

            setattr(profile, field_name, response["public_id"])
            setattr(profile, f"{field_name}_url", response["url"])
        profile.save()

        logger.info(f"Photos for {profile.user.email}'s uploaded successfully")
    except Exception as e:
        logger.error(f"Failed ot upload photos for profile {profile_id}:{str(e)}")

        # clean up any files
        for photo_data in photos.values():
            if photo_data["type"] == "file" and default_storage.exists(
                photo_data["path"]
            ):
                default_storage.delete(photo_data["path"])
