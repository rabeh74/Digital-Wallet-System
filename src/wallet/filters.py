from django_filters import rest_framework as filters
from django_filters import OrderingFilter
from django.db.models import Q
from .models import Wallet, Transaction
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

User = get_user_model()


class WalletFilter(filters.FilterSet):
    """
    FilterSet for Wallet model that allows filtering by:
    - user (username exact match or ID)
    - balance (range, exact)
    - creation date (range)
    - is_active (boolean)
    """
    user = filters.CharFilter(
        method='filter_user',
        label='User (username exact match or ID)',
        help_text='Filter by username (case-insensitive exact) or user ID'
    )
    balance = filters.RangeFilter(
        label='Balance range',
        help_text='Filter by balance range (e.g., balance_min=10&balance_max=100)'
    )
    created_at = filters.DateTimeFromToRangeFilter(
        label='Creation date range',
        help_text='Filter by creation date range (e.g., created_at_after=2023-01-01&created_at_before=2023-12-31)'
    )
    is_active = filters.BooleanFilter(
        field_name='is_active',
        label='Is active',
        help_text='Filter by active status (true/false)'
    )

    ordering = OrderingFilter(
        fields=(
            ('balance', 'balance'),
            ('created_at', 'created_at'),
            ('user__username', 'username'),
            ('is_active', 'is_active'),
        ),
        field_labels={
            'balance': 'Balance',
            'created_at': 'Creation Date',
            'user__username': 'Username',
            'is_active': 'Active Status',
        },
        help_text='Order results by: balance, created_at, username, is_active'
    )

    class Meta:
        model = Wallet
        fields = {
            'balance': ['exact', 'gte', 'lte'],
            'created_at': ['exact', 'gte', 'lte'],
            'is_active': ['exact'],
        }

    def filter_user(self, queryset, name, value):
        """Filter by username (case-insensitive) or user ID"""
        try:
            # Try to filter by user ID if value is numeric
            if value.isdigit():
                return queryset.filter(user__id=value)
            # Otherwise filter by username
            return queryset.filter(user__username__iexact=value)
        except (ValueError, TypeError):
            return queryset.none()


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
    - involving user (sender or recipient by username or ID)
    - sender (username or ID exact match)
    - recipient (username or ID exact match)
    - is_expired (boolean)
    """
    sender = filters.CharFilter(
        method='filter_sender',
        label='Sender (username or ID)',
        help_text='Filter by sender username (case-insensitive) or user ID'
    )
    recipient = filters.CharFilter(
        method='filter_recipient',
        label='Recipient (username or ID)',
        help_text='Filter by recipient username (case-insensitive) or user ID'
    )
    amount = filters.RangeFilter(
        label='Amount range',
        help_text='Filter by amount range (e.g., amount_min=10&amount_max=100)'
    )
    transaction_type = filters.ChoiceFilter(
        choices=Transaction.TransactionTypes.choices,
        label='Transaction type',
        help_text=f'Filter by transaction type: {[choice[0] for choice in Transaction.TransactionTypes.choices]}'
    )
    funding_source = filters.ChoiceFilter(
        choices=Transaction.FundingSource.choices,
        label='Funding source',
        null_label='None',
        help_text=f'Filter by funding source: {[choice[0] for choice in Transaction.FundingSource.choices]}'
    )
    status = filters.ChoiceFilter(
        choices=Transaction.Status.choices,
        label='Transaction status',
        help_text=f'Filter by status: {[choice[0] for choice in Transaction.Status.choices]}'
    )
    reference = filters.CharFilter(
        lookup_expr='icontains',
        label='Reference',
        help_text='Filter by reference (case-insensitive contains)'
    )
    created_at = filters.DateTimeFromToRangeFilter(
        label='Creation date range',
        help_text='Filter by creation date range'
    )
    expiry_time = filters.DateTimeFromToRangeFilter(
        label='Expiry time range',
        help_text='Filter by expiry time range (for pending transactions)'
    )
    involving_user = filters.CharFilter(
        method='filter_involving_user',
        label='Involving user',
        help_text='Filter transactions involving a specific user (sender or recipient) by username or ID'
    )
    is_expired = filters.BooleanFilter(
        method='filter_is_expired',
        label='Is expired',
        help_text='Filter expired transactions (true/false)'
    )

    ordering = OrderingFilter(
        fields=(
            ('amount', 'amount'),
            ('created_at', 'created_at'),
            ('expiry_time', 'expiry_time'),
            ('transaction_type', 'transaction_type'),
            ('status', 'status'),
            ('wallet__user__username', 'sender_username'),
            ('related_wallet__user__username', 'recipient_username'),
        ),
        field_labels={
            'amount': 'Amount',
            'created_at': 'Creation Date',
            'expiry_time': 'Expiry Time',
            'transaction_type': 'Transaction Type',
            'status': 'Status',
            'wallet__user__username': 'Sender Username',
            'related_wallet__user__username': 'Recipient Username',
        },
        help_text='Order results by: amount, created_at, expiry_time, transaction_type, status, sender_username, recipient_username'
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
        try:
            if value.isdigit():
                return queryset.filter(
                    Q(wallet__user__id=value) |
                    Q(related_wallet__user__id=value)
                )
            return queryset.filter(
                Q(wallet__user__username__iexact=value) |
                Q(related_wallet__user__username__iexact=value)
            )
        except (ValueError, TypeError):
            return queryset.none()

    def filter_sender(self, queryset, name, value):
        """Filter by sender username (case-insensitive) or ID"""
        try:
            if value.isdigit():
                return queryset.filter(wallet__user__id=value)
            return queryset.filter(wallet__user__username__iexact=value)
        except (ValueError, TypeError):
            return queryset.none()

    def filter_recipient(self, queryset, name, value):
        """Filter by recipient username (case-insensitive) or ID"""
        try:
            if value.isdigit():
                return queryset.filter(related_wallet__user__id=value)
            return queryset.filter(related_wallet__user__username__iexact=value)
        except (ValueError, TypeError):
            return queryset.none()

    def filter_is_expired(self, queryset, name, value):
        """Filter transactions by expired status"""
        from django.utils import timezone
        now = timezone.now()
        if value:
            return queryset.filter(expiry_time__lt=now)
        return queryset.filter(Q(expiry_time__gte=now) | Q(expiry_time__isnull=True))