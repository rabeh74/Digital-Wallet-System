# from rest_framework import serializers
# from .models import Wallet, Transaction
# from user.serializers import UserSerializer

# class WalletSerializer(serializers.ModelSerializer):
#     user = UserSerializer(read_only=True)
#     class Meta:
#         model = Wallet
#         fields = ['id','user', 'balance', 'created_at']
#         read_only_fields = ['id', 'balance', 'created_at']

# class DepositSerializer(serializers.Serializer):
#     amount = serializers.DecimalField(max_digits=12, decimal_places=2)
#     funding_source = serializers.ChoiceField(choices=Transaction.FundingSource.choices)
#     reference = serializers.CharField(max_length=100)

# class WithdrawalSerializer(serializers.Serializer):
#     amount = serializers.DecimalField(max_digits=12, decimal_places=2)
#     funding_source = serializers.ChoiceField(choices=Transaction.FundingSource.choices)
#     reference = serializers.CharField(max_length=100)

# class TransferSerializer(serializers.Serializer):
#     amount = serializers.DecimalField(max_digits=12, decimal_places=2)
#     recipient_username = serializers.CharField(max_length=150)
#     reference = serializers.CharField(max_length=100, required=False)


# class TransactionSerializer(serializers.ModelSerializer):
#     user = UserSerializer(read_only=True)
#     recipient_user = UserSerializer(read_only=True)
    
#     class Meta:
#         model = Transaction
#         fields = [
#             'id',
#             'recipient_user',
#             'amount',
#             'transaction_type',
#             'funding_source',
#             'reference',
#             'user',
#             'status',
#             'created_at'
#         ]
#         read_only_fields = [
#             'id',
#             'wallet',
#             'status',
#             'created_at'
#         ]
    
# class TransactionActionSerializer(serializers.Serializer):
#     action = serializers.ChoiceField(choices=['accept', 'reject'])
#     reference = serializers.CharField()

# class PaysendWebhookSerializer(serializers.Serializer):
#     transactionId = serializers.CharField(required=True)
#     recipient = serializers.DictField(required=True)
#     amount = serializers.DecimalField(max_digits=12, decimal_places=2, required=True)
#     status = serializers.CharField(required=True)
    
#     def validate(self, data):
#         if data['status'] != 'COMPLETED':
#             raise serializers.ValidationError({"detail": "Transaction not completed"})
        
#         if not data['recipient'].get('phone_number'):
#             raise serializers.ValidationError({"detail": "Phone number not provided"})
        
#         return data
    
# class CashOutRequestSerializer(serializers.Serializer):
#     amount = serializers.DecimalField(
#         max_digits=10, 
#         decimal_places=2,
#     )

# class CashOutVerifySerializer(serializers.Serializer):
#     phone_number = serializers.CharField(max_length=15 , required=True)
#     withdrawal_code = serializers.CharField(max_length=20 , required=True)

# wallet/serializers.py
from rest_framework import serializers
from django.utils import timezone
from .models import Wallet, Transaction
from user.serializers import UserSerializer
from django.contrib.auth import get_user_model
from .exceptions import CustomValidationError

User = get_user_model()


class WalletSerializer(serializers.ModelSerializer):
    """Serializer for Wallet model, including user details."""
    user = UserSerializer(read_only=True)
    currency = serializers.ChoiceField(choices=Wallet.Currencies.choices)

    class Meta:
        model = Wallet
        fields = ['id', 'user', 'balance', 'currency', 'phone_number', 'created_at']
        read_only_fields = ['id', 'balance', 'created_at']


class DepositSerializer(serializers.Serializer):
    """Serializer for deposit transaction data with validation."""
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    funding_source = serializers.ChoiceField(choices=Transaction.FundingSource.choices)
    reference = serializers.CharField(max_length=100)

    def validate_amount(self, value):
        """Ensure amount is positive."""
        if value <= 0:
            raise CustomValidationError("Amount must be positive")
        return value


class WithdrawalSerializer(serializers.Serializer):
    """Serializer for withdrawal transaction data with validation."""
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    funding_source = serializers.ChoiceField(choices=Transaction.FundingSource.choices)
    reference = serializers.CharField(max_length=100)

    def validate_amount(self, value):
        """Ensure amount is positive."""
        if value <= 0:
            raise CustomValidationError("Amount must be positive")
        return value


class TransferSerializer(serializers.Serializer):
    """Serializer for transfer transaction data with validation."""
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    recipient_username = serializers.CharField(max_length=150)
    reference = serializers.CharField(max_length=100, required=False)

    def validate(self, data):
        """Validate transfer-specific conditions."""
        sender = self.context['request'].user
        recipient_username = data['recipient_username']
        amount = data['amount']

        # Validate amount
        if amount <= 0:
            raise CustomValidationError("Amount must be positive")

        # Validate sender wallet exists and has sufficient funds
        try:
            sender_wallet = Wallet.objects.get(user=sender)
            if sender_wallet.balance < amount:
                raise CustomValidationError("Insufficient funds")
        except Wallet.DoesNotExist:
            raise CustomValidationError("Sender wallet not found")

        # Validate recipient exists and isn’t the sender
        try:
            recipient = User.objects.get(username=recipient_username)
            if recipient == sender:
                raise CustomValidationError("Cannot transfer to yourself")
        except User.DoesNotExist:
            raise CustomValidationError(f"User {recipient_username} does not exist")

        return data


class TransactionSerializer(serializers.ModelSerializer):
    """Serializer for Transaction model, including user and recipient details."""
    wallet = WalletSerializer(read_only=True)
    recipient_wallet = WalletSerializer(read_only=True)

    class Meta:
        model = Transaction
        fields = [
            'id',
            'recipient_wallet',
            'amount',
            'transaction_type',
            'funding_source',
            'reference',
            'wallet',
            'status',
            'created_at'
        ]
        read_only_fields = ['id', 'status', 'created_at']


class TransactionActionSerializer(serializers.Serializer):
    """Serializer for transaction action (accept/reject) with validation."""
    action = serializers.ChoiceField(choices=['accept', 'reject'])
    reference = serializers.CharField(max_length=100)

    def validate(self, data):
        """Validate transaction action conditions."""
        reference = data['reference']
        user = self.context['request'].user
        action = data['action']

        # Fetch sender and recipient transactions
        sender_tx = Transaction.objects.filter(
            reference=reference,
            transaction_type=Transaction.TransactionTypes.DEBIT,
            status=Transaction.Status.PENDING
        ).first()
        recipient_tx = Transaction.objects.filter(
            reference=reference,
            transaction_type=Transaction.TransactionTypes.CREDIT,
            status=Transaction.Status.PENDING
        ).first()

        if not sender_tx or not recipient_tx:
            raise CustomValidationError("Pending transaction not found")

        # Only recipient can accept/reject
        if recipient_tx.wallet.user != user:
            raise CustomValidationError("You can only accept/reject your own transactions")

        return data


class PaysendWebhookSerializer(serializers.Serializer):
    """Serializer for Paysend webhook payload with validation."""
    transactionId = serializers.CharField(required=True)
    recipient = serializers.DictField(required=True)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, required=True)
    status = serializers.CharField(required=True)

    def validate(self, data):
        """Validate webhook payload and idempotency."""
        if data['status'] != 'COMPLETED':
            raise CustomValidationError("Transaction not completed")

        if not data['recipient'].get('phone_number'):
            raise CustomValidationError("Phone number not provided")

        if data['amount'] <= 0:
            raise CustomValidationError("Amount must be positive")

        reference = f"Paysend: {data['transactionId']}"
        if Transaction.objects.filter(reference=reference).exists():
            raise CustomValidationError("Transaction already processed")

        phone_number = data['recipient']['phone_number']
        if not Wallet.objects.filter(user__phone_number=phone_number).exists():
            raise CustomValidationError("Wallet not found for phone number")

        return data


class CashOutRequestSerializer(serializers.Serializer):
    """Serializer for cash-out request data with validation."""
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)

    def validate(self, data):
        """Validate cash-out request conditions."""
        amount = data['amount']
        user = self.context['request'].user

        if amount <= 0:
            raise CustomValidationError("Amount must be positive")

        try:
            wallet = Wallet.objects.get(user=user)
            if wallet.balance < amount:
                raise CustomValidationError("Insufficient funds")
        except Wallet.DoesNotExist:
            raise CustomValidationError("Wallet not found")

        return data


class CashOutVerifySerializer(serializers.Serializer):
    """Serializer for cash-out verification data with validation."""
    phone_number = serializers.CharField(max_length=15, required=True)
    withdrawal_code = serializers.CharField(max_length=20, required=True)

    def validate(self, data):
        """Validate cash-out verification conditions."""
        phone_number = data['phone_number']
        withdrawal_code = data['withdrawal_code']

        transaction = Transaction.objects.select_for_update().filter(
            wallet__user__phone_number=phone_number,
            reference__endswith=withdrawal_code,
            status=Transaction.Status.PENDING
        ).first()

        if not transaction:
            raise CustomValidationError("Invalid withdrawal code or phone number")

        if timezone.now() > transaction.expiry_time:
            raise CustomValidationError("Withdrawal code has expired")

        wallet = transaction.user.wallet
        if wallet.balance < abs(transaction.amount):
            raise CustomValidationError("Insufficient funds")

        return data