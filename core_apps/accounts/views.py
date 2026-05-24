from typing import Any
from django.utils import timezone
from rest_framework import generics, status, serializers
from rest_framework.request import Request
from rest_framework.response import Response
from core_apps.common.permissions import IsAccountExecutive
from core_apps.common.permissions import IsTeller
from core_apps.common.renderer import GenericJSONRenderer
from .emails import (
    send_deposit_email,
    send_full_activation_email,
    send_transfer_otp_email,
    send_withdrawal_email,
)
from .models import BankAccount, Transaction
from .serializer import (
    AccountVerificationSerializer,
    CustomerInfoSerializer,
    AccountVerificationSerializer,
    DepositSerializer,
    UsernameVerificationSerializer,
    TransactionSerializer,
)
from django.db import transaction
from loguru import logger
from django.core.exceptions import ValidationError
from decimal import Decimal


class AccountVerificationView(generics.UpdateAPIView):
    queryset = BankAccount.objects.all()
    serializer_class = AccountVerificationSerializer
    renderer_classes = [GenericJSONRenderer]
    object_label = "verification"
    permission_classes = [IsAccountExecutive]

    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        instance = self.get_object()

        if instance.kyc_verified and instance.fully_activated:
            return Response(
                {"message": "Account already verifield and fully activated"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        partial = kwargs.pop("partial", False)
        serializer = self.get_serializer(instance, data=request.data, partial=partial)

        if serializer.is_valid(raise_exception=True):
            kyc_submitted = serializer.validated_data.get(
                "kyc_submitted", instance.kyc_submitted
            )

            kyc_verified = serializer.validated_data.get(
                "kyc_verified", instance.kyc_verified
            )

        if kyc_verified and not kyc_submitted:
            return Response(
                {"error": "KYC submitted is required when verifying an account"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        instance.kyc_submitted = kyc_submitted
        instance.save()

        if kyc_submitted and kyc_verified:
            instance.kyc_verified = kyc_verified

            instance.verification_date = serializer.validated_data.get(
                "verification_date", timezone.now()
            )
            instance.verification_notes = serializer.validated_data.get(
                "verification_notes", ""
            )
            instance.save()

            instance.verified_by = request.user
            instance.fully_activated = True
            instance.account_status = BankAccount.AccountStatus.ACTIVE
            send_full_activation_email(instance)
            instance.save()

            return Response(
                {
                    "message": "Account verification status updated successfully",
                    "data": self.get_serializer(instance).data,
                },
                status=status.HTTP_200_OK,
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class DepositView(generics.CreateAPIView):
    serializer_class = DepositSerializer
    renderer_classes = [GenericJSONRenderer]
    object_label = "deposit"
    permission_classes = [IsTeller]

    # retrieve customer infor using account number
    def get(sef, request: Request, *args: Any, **kwargs: Any) -> Response:
        account_number = request.query_params.get("account_number")

        if not account_number:
            return Response(
                {"error": "Account number is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            account = BankAccount.objects.get(account_number=account_number)
            serializer = CustomerInfoSerializer(account)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except BankAccount.DoesNotExist:
            return Response(
                {"error": "Account does not exist"},
                status=status.HTTP_404_NOT_FOUND,
            )

    @transaction.atomic()
    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        amount = serializer.validated_data["amount"]
        account = serializer.context.get("account")

        if not account:
            return Response({"error": "Account not found"}, status=400)

        try:
            account.account_balance += amount

            try:
                account.full_clean()
            except ValidationError as e:
                return Response({"error": e.message_dict}, status=400)

            account.save()
            logger.info(
                f"Deposit of {amount} made to {account.account_number} by {request.user.email} successful"
            )

            try:
                send_deposit_email(
                    user=account.user,
                    user_email=account.user.email,
                    amount=amount,
                    currency=account.currency,
                    new_balance=account.account_balance,
                    account_number=account.account_number,
                )

            except Exception:
                logger.exception("Deposit succeeded but email failed")

            return Response(
                {
                    "message": f"Deposit successful of {str(amount)}  to {account.account_number}",
                    "new_balance": str(account.account_balance),
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            logger.error(f"Failed to deposit: Error: {str(e)}")
            return Response(
                {"error": "An error occurred while depositing"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class InitiateWidhrawalView(generics.CreateAPIView):
    serializer_class = TransactionSerializer
    renderer_classes = [GenericJSONRenderer]
    object_label = "initiate_withdrawal"

    def create(self, request: Request, *args: Any, **kwargs) -> Response:
        account_number = request.data.get("account_number")
        amount = request.data.get("amount")

        if not account_number:
            return Response(
                {"error": "Account number is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            account = BankAccount.objects.get(
                account_number=account_number, user=request.user
            )

            if not (account.fully_activated and account.kyc_verified):
                return Response(
                    {
                        "error": "Account not fully activated or KYC not verified plaese complete the verification process"
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
        except BankAccount.DoesNotExist:
            return Response(
                {"error": "Account does not exist"},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.get_serializer(
            data={
                "amount": amount,
                "description": f"Withdrawal of {amount} from {account_number}",
                "receiver": request.user.id,
                "transaction_type": Transaction.TransactionType.WITHDRAWAL,
                "sender_account": account_number,
                "receiver_account": account_number,
            }
        )

        try:
            serializer.is_valid(raise_exception=True)

        except serializers.ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        amount = serializer.validated_data["amount"]

        if account.account_balance < amount:
            return Response(
                {"error": "Insufficient funds for withdrawal"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        request.session["withdrawal_data"] = {
            "account_number": account_number,
            "amount": str(amount),
        }

        logger.info(
            f"Initiated info of {amount} from {account_number} by {request.user.email} stored in a session"
        )

        return Response(
            {
                "message": f"Initiated info of {amount} from {account_number} by {request.user.email} stored in a session",
                "next_step": "Verify your username to complete the widhdrawal",
            },
            status=status.HTTP_200_OK,
        )


class VerifyUsernameAndwithdrawAPIView(generics.CreateAPIView):
    serializer_class = UsernameVerificationSerializer
    renderer_classes = [GenericJSONRenderer]
    object_label = "verify_username_and_widhdrawal"

    @transaction.atomic
    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:

        serializer = self.get_serializer(
            data=request.data, context={"request": request}
        )

        try:
            serializer.is_valid(raise_exception=True)
        except serializers.ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        withdrawal_data = request.session.get("withdrawal_data")

        if not withdrawal_data:
            return Response(
                {
                    "error": "No pending withdrawal data found, please initiate a withdrawal first"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        account_number = withdrawal_data.get("account_number")
        amount = Decimal(withdrawal_data.get("amount"))

        try:
            account = BankAccount.objects.get(
                account_number=account_number, user=request.user
            )
        except BankAccount.DoesNotExist:
            return Response(
                {
                    "error": f"Account of account number {account_number}  does not exist"
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if account.account_balance < amount:
            return Response(
                {"error": "Insufficient funds for withdrawal"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        account.account_balance -= amount
        account.save()

        withdraw_transaction = Transaction.objects.create(
            amount=amount,
            sender=request.user,
            receiver=request.user,
            transaction_type=Transaction.TransactionType.WITHDRAWAL,
            description=f"Withdrawal of {amount} from {account_number}",
            sender_account=account,
            status=Transaction.TransactionStatus.COMPLETED,
        )

        logger.info(
            f"Withdrawal of {amount} from {account_number} by {request.user.email} successful"
        )

        send_withdrawal_email(
            user=request.user,
            user_email=request.user.email,
            amount=amount,
            currency=account.currency,
            new_balance=account.account_balance,
            account_number=account_number,
        )

        del request.session["withdrawal_data"]

        return Response(
            {
                "message": f"Withdrawal of {amount} from {account_number} by {request.user.email} successful",
                "transaction": TransactionSerializer(withdraw_transaction).data,
            },
            status=status.HTTP_200_OK,
        )
