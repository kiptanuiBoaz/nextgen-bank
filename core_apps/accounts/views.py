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
    send_transfer_email,
    send_transfer_otp_email,
    send_withdrawal_email,
)
from .models import BankAccount, Transaction
from .serializer import (
    AccountVerificationSerializer,
    CustomerInfoSerializer,
    OTPVerificationSerializer,
    SecurityQuestionSerializer,
    DepositSerializer,
    UsernameVerificationSerializer,
    TransactionSerializer,
)
from django.db import transaction
from loguru import logger
from django.core.exceptions import ValidationError
from decimal import Decimal
import random
from .pagination import StandardResultsSetPagination
from django_filters.rest_framework import DjangoFilterBackend, OrderingFilter
from dateutil import parser
from django.db.models import Q


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


class InitiateTransferView(generics.CreateAPIView):
    serializer_class = TransactionSerializer
    renderer_classes = [GenericJSONRenderer]
    object_label = "initiate_transfer"

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        data = request.data.copy()
        data["transaction_type"] = Transaction.TransactionType.TRANSFER

        sender_account_number = data.get("sender_account")
        receiver_account_number = data.get("receiver_account")

        try:
            sender_account = BankAccount.objects.get(
                account_number=sender_account_number, user=request.user
            )
            if not (sender_account.fully_activated and sender_account.kyc_verified):
                return Response(
                    {
                        "error": "This account is not fully verified. Please complete the "
                        "verification process, by visiting any of our local bank branches"
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
        except BankAccount.DoesNotExist:
            return Response(
                {
                    "error": "Sender account number not found or you're not authorized to use "
                    "this account."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.get_serializer(data=data)

        if serializer.is_valid():
            request.session["transfer_data"] = {
                "sender_account": sender_account_number,
                "receiver_account": receiver_account_number,
                "amount": str(serializer.validated_data["amount"]),
                "description": serializer.validated_data.get("description", ""),
            }
            return Response(
                {
                    "message": "Please answer your security question to proceed with the transfer",
                    "next_step": "verify security question",
                },
                status=status.HTTP_200_OK,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class VerifySecurityQuestionView(generics.CreateAPIView):
    serializer_class = SecurityQuestionSerializer
    renderer_classes = [GenericJSONRenderer]
    object_label = "verification_answer"

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(
            data=request.data, context={"request": request}
        )
        if serializer.is_valid():
            otp = "".join([str(random().randint(0, 9)) for _ in range(6)])
            request.user.set_otp(otp)
            send_transfer_otp_email(request.user.email, otp)
            return Response(
                {
                    "message": "Security question verified. An OTP has been sent to your email",
                    "next_step": "verify otp",
                },
                status=status.HTTP_200_OK,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class VerifyOTPView(generics.CreateAPIView):
    serializer_class = OTPVerificationSerializer()
    renderer_classes = [GenericJSONRenderer]
    object_label = "verify_otp"

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(
            data=request.data, context={"request": request}
        )
        if serializer.is_valid():
            return self.process_transfer(request)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def process_transfer(self, request) -> Response:
        transfer_data = request.session.get("transfer_data")
        if not transfer_data:
            return Response(
                {"error": "Transfer data not found. Please start the process again."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            sender_account = BankAccount.objects.get(
                account_number=transfer_data["sender_account"]
            )
            receiver_account = BankAccount.objects.get(
                account_number=transfer_data["receiver_account"]
            )
        except BankAccount.DoesNotExist:
            return Response(
                {"error": "One or both accounts not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        amount = Decimal(transfer_data["amount"])

        if sender_account.account_balance < amount:
            return Response(
                {"error": "Insufficient funds for transfer"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        sender_account.account_balance -= amount
        receiver_account.account_balance += amount
        sender_account.save()
        receiver_account.save()

        transfer_transaction = Transaction.objects.create(
            user=request.user,
            sender=request.user,
            sender_account=sender_account,
            receiver=receiver_account.user,
            receiver_account=receiver_account,
            amount=amount,
            description=transfer_data.get("description", ""),
            transaction_type=Transaction.TransactionType.TRANSFER,
            status=Transaction.TransactionStatus.COMPLETED,
        )

        del request.session["transfer_data"]

        send_transfer_email(
            sender_name=sender_account.user.full_name,
            sender_email=sender_account.user.email,
            receiver_name=receiver_account.user.full_name,
            receiver_email=receiver_account.user.email,
            amount=amount,
            currency=sender_account.currency,
            sender_new_balance=sender_account.account_balance,
            receiver_new_balance=receiver_account.account_balance,
            sender_account_number=sender_account.account_number,
            receiver_account_number=receiver_account.account_number,
        )

        logger.info(
            f"Transfer of {amount} made from account {sender_account.account_number} to "
            f"{receiver_account.account_number}"
        )

        return Response(
            TransactionSerializer(transfer_transaction).data,
            status=status.HTTP_201_CREATED,
        )


class TransactionListAPIView(generics.ListAPIView):
    serializer_class = TransactionSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    ordering_fields = ["created_at", "amount"]
    ordering = ["-created_at"]

    def get_queryset(self):
        user = self.request.user
        queryset = Transaction.objects.filter(
            Q(sender=user) | Q(receiver=user)
        ).order_by("-created_at")
        start_date = self.request.query_params.get("start_date")
        end_date = self.request.query_params.get("end_date")
        account_number = self.request.query_params.get("account_number")

        if start_date:
            try:
                start_date = parser.parse(start_date)
                queryset = queryset.filter(created_at__gte=start_date)
            except ValueError:
                pass

        if end_date:
            try:
                end_date = parser.parse(end_date)
                queryset = queryset.filter(created_at__lte=end_date)
            except ValueError:
                pass

        if account_number:
            try:
                account = BankAccount.objects.get(
                    account_number=account_number, user=user
                )
                queryset = queryset.filter(
                    Q(sender_account=account) | Q(receiver_account=account)
                )
            except BankAccount.DoesNotExist:
                queryset = Transaction.objects.none()

    def list(self, request, *args, **kwargs) -> Response:
        response = super().list(request, *args, **kwargs)
        account_number = request.query_params.get("account_number")

        if account_number:
            logger.info(
                f"User {request.user.email} retrieved transactions for account {account_number}"
            )
        else:
            logger.info(
                f"User {request.user.email} retrieved transactions for all accounts"
            )

        return response
