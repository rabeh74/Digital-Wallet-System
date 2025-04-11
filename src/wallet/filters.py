# wallet/filters.py
from django_filters import rest_framework as filters
from django_filters import OrderingFilter
from django.db.models import Q
from .models import Wallet, Transaction
from django.contrib.auth import get_user_model

User = get_user_model()

class WalletFilter(filters.FilterSet):
    """
    FilterSet for Wallet model that allows filtering by:
    - user (username exact match)
    - balance (range, exact)
    - creation date (range)
    """
    user = filters.CharFilter(field_name="user__username", lookup_expr='iexact', label='User username (exact match)')
    balance = filters.RangeFilter(label='Balance range')
    created_at = filters.DateTimeFromToRangeFilter(label='Creation date range')

    ordering = OrderingFilter(
        fields=(
            ('balance', 'balance'),
            ('created_at', 'created_at'),
            ('user__username', 'username'),
        ),
        field_labels={
            'balance': 'Balance',
            'created_at': 'Creation Date',
            'user__username': 'Username',
        }
    )

    class Meta:
        model = Wallet
        fields = {
            'user': ['exact'],
            'balance': ['exact', 'gte', 'lte'],
            'created_at': ['exact', 'gte', 'lte'],
        }


class TransactionFilter(filters.FilterSet):
    """
    FilterSet for Transaction model that allows filtering by:
    - amount (range, exact)
    - transaction_type (exact match)
    - funding_source (exact match)
    - status (exact match)
    - reference (contains)
    - creation date (range)
    - expiry time (range)
    - involving user (sender or recipient)
    - sender (username exact match)
    - recipient (username exact match)
    """
    sender = filters.CharFilter(field_name="wallet__user__username", lookup_expr='iexact', label='Sender username (exact match)')
    recipient = filters.CharFilter(field_name="related_wallet__user__username", lookup_expr='iexact', label='Recipient username (exact match)')
    amount = filters.RangeFilter(label='Amount range')
    transaction_type = filters.ChoiceFilter(
        choices=Transaction.TransactionTypes.choices,
        label='Transaction type'
    )
    funding_source = filters.ChoiceFilter(
        choices=Transaction.FundingSource.choices,
        label='Funding source'
    )
    status = filters.ChoiceFilter(
        choices=Transaction.Status.choices,
        label='Transaction status'
    )
    reference = filters.CharFilter(lookup_expr='icontains', label='Reference (case-insensitive contains)')
    created_at = filters.DateTimeFromToRangeFilter(label='Creation date range')
    expiry_time = filters.DateTimeFromToRangeFilter(label='Expiry time range')
    involving_user = filters.CharFilter(
        method='filter_involving_user',
        label='Transactions involving a specific user (sender or recipient)'
    )

    ordering = OrderingFilter(
        fields=(
            ('amount', 'amount'),
            ('created_at', 'created_at'),
            ('expiry_time', 'expiry_time'),
            ('transaction_type', 'transaction_type'),
            ('status', 'status'),
        ),
        field_labels={
            'amount': 'Amount',
            'created_at': 'Creation Date',
            'expiry_time': 'Expiry Time',
            'transaction_type': 'Transaction Type',
            'status': 'Status',
        }
    )

    class Meta:
        model = Transaction
        fields = {
            'amount': ['exact', 'gte', 'lte'],
            'transaction_type': ['exact'],
            'funding_source': ['exact'],
            'status': ['exact'],
            'reference': ['exact', 'icontains'],
            'created_at': ['exact', 'gte', 'lte'],
            'expiry_time': ['exact', 'gte', 'lte'],
        }

    def filter_involving_user(self, queryset, name, value):
        """Filter transactions where the user is either the sender or recipient"""
        return queryset.filter(
            Q(wallet__user__username__iexact=value) |
            Q(related_wallet__user__username__iexact=value)
        )