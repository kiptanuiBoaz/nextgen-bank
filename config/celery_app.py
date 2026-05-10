import os

from celery import Celery
from django.conf import settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")


# instanciate celery
app = Celery("nextgen_bank")

# load configurations  from django settings module and add a namespace to prevent conflict
app.config_from_object("django.conf:settings", namespace="CELERY")

# automatically discover tasks in all installed django apps
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)
