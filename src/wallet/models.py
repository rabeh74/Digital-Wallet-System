from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator

User = get_user_model()

class Wallet(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='wallet')
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, validators=[MinValueValidator(0)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


    def __str__(self):
        return f"{self.user.username}'s Wallet (Balance: {self.balance})"

class Transaction(models.Model):
    TRANSACTION_TYPE = (
        ('DEP', 'Deposit'),
        ('WTH', 'Withdrawal'),
        ('TRF', 'Transfer')
    )
    
    FUNDING_SOURCE = (
        ('BANK', 'Bank Transfer'),
        ('CARD', 'Card Payment'),
        ('CASH', 'Cash Deposit'),
        ('MOBILE', 'Mobile Money'),
        ('PEER', 'Peer Transfer'),
        ('PROMO', 'Promotional Credit'),
        ('REFUND', 'Refund')
    )
    
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name='transactions')
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0.01)])
    transaction_type = models.CharField(max_length=3, choices=TRANSACTION_TYPE)
    funding_source = models.CharField(max_length=10, choices=FUNDING_SOURCE, null=True, blank=True)
    reference = models.CharField(max_length=100)
    recipient = models.ForeignKey(Wallet, on_delete=models.SET_NULL, null=True, blank=True, related_name='received_transactions')
    status = models.CharField(max_length=20, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.get_transaction_type_display()} of {self.amount} for {self.wallet.user.username}"