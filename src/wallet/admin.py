# wallet/admin.py
from django.contrib import admin
from .models import Transaction, Wallet  # Assuming a Wallet model

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('reference', 'transaction_type', 'amount', 'wallet', 'related_wallet', 'status', 'created_at')
    list_filter = ('transaction_type', 'status', 'created_at')
    search_fields = ('reference', 'wallet__user__username', 'related_wallet__user__username')
    ordering = ('-created_at',)

@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ('user', 'balance', 'currency', 'phone_number', 'is_active', 'created_at', 'updated_at')
    search_fields = ('user__username', 'phone_number')