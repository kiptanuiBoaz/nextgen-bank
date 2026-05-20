import secrets

from django.db import transaction
from .emails import send_account_creation_email
from django.conf import settings
from typing import Any, Union, List

from .models import BankAccount


def generate_account_number(currency: str) -> str:
    bank_code = settings.BANK_CODE
    branch_code = settings.BANK_BRANCH_CODE

    currency_codes = {
        "us_dollar": settings.CURRENCY_CODE_USD,
        "pound_sterling": settings.CURRENCY_CODE_GBP,
        "kenya_shilling": settings.CURRENCY_CODE_KES,
    }

    currency_code = currency_codes.get(currency)

    if not currency_code:
        raise ValueError(f"Invalid currency: {currency}")

    acc_prefix = f"{bank_code}{branch_code}{currency_code}"
    remainig_digits = 6 - len(acc_prefix) - 1

    # cryptpgraphically secure
    random_digits = "".join(
        secrets.choice(("0123456789")) for _ in range(remainig_digits)
    )
    partial_account_number = f"{acc_prefix}{random_digits}"

    check_digit = calculate_luhn_check_digit(partial_account_number)
    account_number = f"{partial_account_number}{check_digit}"

    return account_number


def calculate_luhn_check_digit(number: str) -> str:
    def split_into_digits(n: Union[str, int]) -> List[int]:
        return [int(digit) for digit in str(n)]

    digits = split_into_digits(number)
    odd_gits = digits[-1::-2]
    even_gits = digits[-2::-2]
    total = sum(odd_gits)

    for d in even_gits:
        doubled = d * 2
        total += sum(split_into_digits(doubled))

    check_digit = (10 - (total % 10)) % 10
    return str(check_digit)


def create_bank_account(user: Any, currency: str, account_type: str) -> Any:
    # context manager - fail together or success together
    with transaction.atomic():
        while True:
            account_number = generate_account_number(currency)

            if not BankAccount.objects.filter(account_number=account_number).exists():
                break

        is_primary = not BankAccount.objects.filter(user=user).exists()

        bank_account = BankAccount.objects.create(
            user=user,
            account_number=account_number,
            currency=currency,
            account_type=account_type,
            is_primary=is_primary,
        )

        send_account_creation_email(user, bank_account)
        return bank_account
