from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class UserProfileConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core_apps.user_profile"
    verbose_name = _("User Profile")

    # egister and connect  signals when user profiles app is loaded by django
    def ready(self) -> None:
        import core_apps.user_profile.signals
