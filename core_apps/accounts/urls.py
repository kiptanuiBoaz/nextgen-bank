from django.urls import path
from .views import (
    AccountVerificationView,
    DepositView,
    InitiateWidhrawalView,
    VerifyOTPView,
    VerifySecurityQuestionView,
    VerifyUsernameAndwithdrawAPIView,
    InitiateTransferView,
    TransactionListAPIView,
    TransactionPDFView,
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
    path(
        "transfer/initiate/",
        InitiateTransferView.as_view(),
        name="initiate_transfer",
    ),
    path(
        "transfer/verify-security-question/",
        VerifySecurityQuestionView.as_view(),
        name="verify_security_question",
    ),
    path(
        "transfer/verify-otp/",
        VerifyOTPView().as_view(),
        name="verify_otp",
    ),
    path(
        "transactions/",
        TransactionListAPIView.as_view(),
        name="transaction_list",
    ),
    path(
        "transactions/pdf/",
        TransactionPDFView.as_view(),
        name="transaction_pdf",
    ),
]
