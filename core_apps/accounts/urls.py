from django.urls import path
from . import views

urlpatterns = [
    path(
        "verify/<uuid:pk>/",
        views.AccountVerificationView.as_view(),
        name="account_verfication",
    ),
]
