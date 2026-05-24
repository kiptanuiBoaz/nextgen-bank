from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from .models import BankAccount, Transaction
from decimal import Decimal


class AccountVerificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankAccount
        fields = [
            "kyc_submitted",
            "kyc_verified",
            "verification_date",
            "fully_activated",
            "account_status",
            "verification_notes",
        ]

        read_only_fields = ["fully_activated"]

        def validate(self, data: dict) -> dict:
            kyc_verified = data.get("kyc_verified")
            kyc_submitted = data.get("kyc_submitted")
            verification_date = data.get("verification_date")
            verification_notes = data.get("verification_notes")

            if kyc_submitted:
                if not verification_date:
                    raise serializers.ValidationError(
                        _("Verification date is required whenb verifying an account")
                    )

                if not verification_notes:
                    raise serializers.ValidationError(
                        _("Verification notes are required when verifying an account")
                    )

            if kyc_submitted and not all(
                [kyc_submitted, verification_date, verification_notes]
            ):
                raise serializers.ValidationError(
                    _(
                        "All verification fields (KYC submitted, verification date, verification notes) are required when verifying an account"
                    )
                )


class DepositSerializer(serializers.ModelSerializer):
    account_number = serializers.CharField(max_length=20, required=True)
    amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal("0.1")
    )

    class Meta:
        model = BankAccount
        fields = ["account_number", "amount"]

    def validate_account_number(self, value: str) -> str:
        try:
            account = BankAccount.objects.get(account_number=value)
            print(account)
            self.context["account"] = account
        except BankAccount.DoesNotExist:
            raise serializers.ValidationError(_("Account does not exist"))
        return value

    # converting decimal from object to string - json serializable
    def to_representation(self, instance: BankAccount) -> str:
        representation = super().to_representation(instance)
        representation["amount"]
        return representation


class CustomerInfoSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="user.full_name")
    email = serializers.EmailField(source="user.email")
    photo_url = serializers.URLField(source="user.photo.url")

    class Meta:
        model = BankAccount
        fields = [
            "account_number",
            "full_name",
            "email",
            "account_balance",
            "photo_url",
            "account_type",
            "currency",
        ]

    def get_photo_url(self, obj):
        if hasattr(obj.user, "profile") and obj.profile.photo_url:
            return obj.user.profile.photo_url

        return None


class UUIDField(serializers.UUIDField):
    # control and modify the output
    def to_representation(self, value: str) -> str:
        return str(value)


class TransactionSerializer(serializers.ModelSerializer):
    id = UUIDField(read_only=True)
    sender_account = serializers.CharField(max_length=20, required=True)
    receiver_account = serializers.CharField(max_length=20, required=True)
    amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal("0.1")
    )

    class Meta:
        model = Transaction
        fields = [
            "id",
            "sender_account",
            "receiver_account",
            "amount",
            "description",
            "created_at",
            "sender",
            "receiver",
            "status",
            "transaction_type",
        ]

        read_only_fields = ["id", "created_at", "status"]

    # convert amount from decimal object to  string
    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation["amount"] = str(representation["amount"])
        representation["sender"] = (
            instance.sender.full_name if instance.sender else None
        )
        representation["receiver"] = (
            instance.receiver.full_name if instance.receiver else None
        )
        representation["sender_account"] = (
            instance.sender_account.account_number if instance.sender_account else None
        )
        representation["receiver_account"] = (
            instance.receiver_account.account_number
            if instance.receiver_account
            else None
        )

        return representation

    def validate(self, data):
        transaction_type = data.get("transaction_type")
        sender_account_number = data.get("sender_account")
        receiver_account_number = data.get("receiver_account")
        amount = data.get("amount")

        try:
            if transaction_type == Transaction.TransactionType.WITHDRAWAL:
                account = BankAccount.objects.get(account_number=sender_account_number)
                data["sender_account"] = account
                data["receiver_account"] = None

                if account.account_balance < amount:
                    raise serializers.ValidationError(
                        _("Insufficient funds for widhrawal ")
                    )
            elif transaction_type == Transaction.TransactionType.DEPOSIT:
                account = BankAccount.objects.get(
                    account_number=receiver_account_number
                )
                data["sender_account"] = None
                data["receiver_account"] = account
            else:
                sender_account = BankAccount.objects.get(
                    account_number=sender_account_number
                )
                receiver_account = BankAccount.objects.get(
                    account_number=receiver_account_number
                )
                data["sender_account"] = sender_account
                data["receiver_account"] = receiver_account

                if sender_account == receiver_account:
                    raise serializers.ValidationError(
                        "Sender and receiver cannot be the same"
                    )

                if sender_account.currencey != receiver_account.currency:
                    raise serializers.ValidationError(
                        "Transfers are only allowed  between accounts of the same currency"
                    )

                if sender_account.account_balance < amount:
                    raise serializers.ValidationError(
                        _("Insufficient funds for transfer")
                    )

        except BankAccount.DoesNotExist:
            raise serializers.ValidationError(_("One or bother account does not exist"))
        return data


class SecurityQuestionSerializer(serializers.ModelSerializer):
    security_answer = serializers.CharField(max_length=30)

    def validate(self, data: dict) -> dict:
        user = self.context["request"].user
        security_question = data.get("security_question")
        security_answer = data.get("security_answer")

        if security_answer != user.security_answer:
            raise serializers.ValidationError(_("Incorrect security answer"))
        return data


class OTPVerifidciationSerializer(serializers.ModelSerializer):
    otp = serializers.CharField(max_length=6)

    def validate(self, data: dict) -> dict:
        user = self.context["request"].user
        otp = data.get("otp")
        if not user.verify_otp(otp):
            raise serializers.ValidationError(_("Invalid or expired OTP"))
        return data


class UsernameVerificationSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=30)

    def validate_username(self, value: str) -> str:
        user = self.context["request"].user

        if value != user.username:
            raise serializers.ValidationError(_("Invalid username"))
        return value
