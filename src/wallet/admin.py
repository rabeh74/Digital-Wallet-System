# wallet/admin.py
from django.contrib import admin
from .models import Transaction, Wallet  # Assuming a Wallet model

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('reference', 'transaction_type', 'amount', 'user', 'related_user', 'status', 'created_at')
    list_filter = ('transaction_type', 'status', 'created_at')
    search_fields = ('reference', 'user__username', 'related_user__username')
    ordering = ('-created_at',)

@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ('user', 'balance')
    search_fields = ('user__username',)