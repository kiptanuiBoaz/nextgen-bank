from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from .models import BankAccount
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
