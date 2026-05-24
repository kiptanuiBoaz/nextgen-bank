from django.urls import path
from .views import (
    AccountVerificationView,
    DepositView,
    InitiateWidhrawalView,
    VerifyUsernameAndwithdrawAPIView,
)

urlpatterns = [
    path(
        "verify/<uuid:pk>/",
        AccountVerificationView.as_view(),
        name="account_verfication",
    ),
    path("deposit/<uuid:pk>/", DepositView.as_view(), name="account_deposit"),
    path(
        "initiate-withdrawal/",
        InitiateWidhrawalView.as_view(),
        name="initiate_withdrawal",
    ),
    path(
        "verify-username-and-withdraw/",
        VerifyUsernameAndwithdrawAPIView.as_view(),
        name="verify_username_and_withdraw",
    ),
]
