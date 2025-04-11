from django.db import models
from django.contrib.auth import get_user_model
from decimal import Decimal

User = get_user_model()

class Wallet(models.Model):
    class Currencies(models.TextChoices):
        USD = 'USD', 'US Dollar'
        EUR = 'EUR', 'Euro'
        GBP = 'GBP', 'British Pound'
        LBP = 'LBP', 'Lebanese Pound'
        
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='wallet')
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    currency = models.CharField(max_length=3, choices=Currencies.choices, default='USD')
    phone_number = models.CharField(max_length=15 , unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['phone_number']),
        ]

    def __str__(self):
        return f"{self.user.username}'s Wallet (Balance: {self.balance})"

class Transaction(models.Model):
    class TransactionTypes(models.TextChoices):
        DEPOSIT = 'DEP', 'Deposit'
        WITHDRAWAL = 'WTH', 'Withdrawal'
        CREDIT = 'CREDIT', 'Credit'
        DEBIT = 'DEBIT', 'Debit'
    
    class FundingSource(models.TextChoices):
        PAYSEND = 'PAYSEND', 'Paysend'
        BLF_ATM = 'BLF_ATM', 'Banque Libano-Française ATM'
        INTERNAL = 'INTERNAL', 'Internal'

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        ACCEPTED = 'ACCEPTED', 'Accepted'
        REJECTED = 'REJECTED', 'Rejected'
        COMPLETED = 'COMPLETED', 'Completed'
        FAILED = 'FAILED', 'Failed'
        EXPIRED = 'EXPIRED', 'Expired'

    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name='transactions' , null=True, blank=True , default=None)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    transaction_type = models.CharField(max_length=10, choices=TransactionTypes.choices)
    funding_source = models.CharField(max_length=10, choices=FundingSource.choices, null=True, blank=True)
    reference = models.CharField(max_length=100 )
    related_wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name='related_transactions' , null=True, blank=True , default=None)
    status = models.CharField(max_length=20, choices=Status.choices, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expiry_time = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['reference']),
            models.Index(fields=['status' , 'created_at'])
        ]
    def __str__(self):
        return f"{self.get_transaction_type_display()} of {self.amount} for {self.wallet.user.username}"
    
    def get_transaction_type_display(self):
        return self.TransactionTypes(self.transaction_type)
        