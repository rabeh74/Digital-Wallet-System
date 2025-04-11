"""
Views for the wallet app, handling wallet management, transactions, transfers,
cash-outs, and webhook integrations using Django REST Framework.
"""
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes, OpenApiExample
from django.core.cache import cache
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django_filters.rest_framework import DjangoFilterBackend
from decimal import Decimal
import hmac
import hashlib
import json
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.db.models import Q
from django.contrib.auth import get_user_model
from rest_framework.generics import GenericAPIView
from .exceptions import CustomValidationError
from .models import Wallet, Transaction
from .serializers import (
    WalletSerializer,
    TransferSerializer,
    TransactionSerializer,
    TransactionActionSerializer,
    PaysendWebhookSerializer,
    CashOutRequestSerializer,
    CashOutVerifySerializer,
)
from .permissions import IsOwner
from .service import WalletServiceFactory
from .filters import WalletFilter, TransactionFilter
from .pagination import TransactionPagination
from .utils import IdempotencyMixin, IdempotencyChecker

User = get_user_model()
CACHE_TIMEOUT = settings.CACHE_TIMEOUT

class BaseServiceViewSet(viewsets.ModelViewSet):
    """Base viewset providing service injection for wallet and transaction services."""

    def __init__(self, wallet_service=None, transaction_service=None, *args, **kwargs):
        """
        Initialize the viewset with wallet and transaction services.

        Args:
            wallet_service: Optional WalletService instance (for testing/mocking).
            transaction_service: Optional TransactionService instance (for testing/mocking).
            *args: Variable length argument list.
            **kwargs: Arbitrary keyword arguments.
        """
        super().__init__(*args, **kwargs)
        factory = WalletServiceFactory()
        self.wallet_service = wallet_service or factory.create_wallet_service()
        self.transaction_service = transaction_service or factory.create_transaction_service()


class WalletViewSet(BaseServiceViewSet):
    """
    Viewset for managing wallets, including creation, retrieval, transfers, and cash-out requests.
    """

    serializer_class = WalletSerializer
    permission_classes = [IsAuthenticated, IsOwner]
    throttle_scope = 'wallet'
    http_method_names = ['get', 'post']
    filterset_class = WalletFilter

    def get_queryset(self):
        """
        Retrieve wallets based on user role.

        Returns:
            QuerySet: Filtered wallets (all for staff, user-specific otherwise).
        """
        queryset = Wallet.objects.select_related('user').all()
        if not self.request.user.is_staff:
            return queryset.filter(user=self.request.user)
        return queryset

    def create(self, request, *args, **kwargs):
        """
        Create a wallet for the authenticated user if it doesn't exist.

        Args:
            request: HTTP request object.
            *args: Variable length argument list.
            **kwargs: Arbitrary keyword arguments.

        Returns:
            Response: Wallet data on success, error message if wallet exists.
        """
        if hasattr(request.user, 'wallet'):
            return Response(
                {'detail': 'Wallet already exists'},
                status=status.HTTP_400_BAD_REQUEST
            )
        wallet = self.wallet_service.create_wallet(request.user)
        serializer = self.get_serializer(wallet)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], serializer_class=TransferSerializer)
    def transfer(self, request):
        """
        Handle fund transfer between wallets.

        Args:
            request: HTTP request with transfer data (recipient_username, amount, reference).

        Returns:
            Response: Success message with reference or error details.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        recipient_username = serializer.validated_data['recipient_username']
        amount = Decimal(serializer.validated_data['amount'])
        reference = serializer.validated_data.get('reference')

        sender_user = request.user
        recipient_user = self._get_recipient_user(recipient_username)
        reference = self._process_transfer(sender_user, recipient_user, amount, reference)
        return Response(
            {'message': 'Transfer initiated successfully', 'reference': reference},
            status=status.HTTP_200_OK
        )

    @action(detail=False, methods=['post'], serializer_class=CashOutRequestSerializer)
    def cash_out_request(self, request):
        """
        Request a cash-out and return a withdrawal code.

        Args:
            request: HTTP request with cash-out data (amount).

        Returns:
            Response: Cash-out details (withdrawal_code, amount, phone_number) or error.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        amount = Decimal(serializer.validated_data['amount'])
        wallet = self._get_user_wallet(request.user)
        withdrawal_code = self.wallet_service.request_cash_out(wallet, amount)
        return Response(
            {
                'message': 'Cash out request created',
                'withdrawal_code': withdrawal_code,
                'amount': str(amount),
                'phone_number': request.user.phone_number
            },
            status=status.HTTP_200_OK
        )

    def _get_user_wallet(self, user):
        """
        Retrieve the user's wallet, raising an error if it doesn’t exist.

        Args:
            user: User instance to fetch wallet for.

        Returns:
            Wallet: User's wallet object.

        Raises:
            CustomValidationError: If no wallet is found.
        """
        if not hasattr(user, 'wallet'):
            raise CustomValidationError("No wallet found for user")
        return user.wallet

    def _get_recipient_user(self, username):
        """
        Fetch the recipient user by username, validating transfer conditions.

        Args:
            username: Username of the recipient.

        Returns:
            User: Recipient user object.

        Raises:
            CustomValidationError: If user doesn’t exist or is the same as the sender.
        """
        try:
            recipient = User.objects.get(username=username)
            if recipient == self.request.user:
                raise CustomValidationError("Cannot transfer to yourself")
            return recipient
        except User.DoesNotExist:
            raise CustomValidationError(f"User with username {username} does not exist")

    def _process_transfer(self, sender, recipient, amount, reference):
        """
        Process the transfer using the wallet service.

        Args:
            sender: User initiating the transfer.
            recipient: User receiving the transfer.
            amount: Decimal amount to transfer.
            reference: Optional transaction reference.

        Returns:
            str: Transaction reference.

        Raises:
            CustomValidationError: If wallet is not found or transfer fails.
        """
        try:
            return self.wallet_service.process(
                process_type='transfer',
                wallet=sender.wallet,
                recipient_wallet=recipient.wallet,
                amount=amount,
                reference=reference
            )
        except Wallet.DoesNotExist:
            raise CustomValidationError("Wallet not found")
    
    @extend_schema(
        summary='List wallets',
        description='List wallets filtered by user, balance, and creation date',
        parameters=[
            OpenApiParameter(
                name='user', 
                type=OpenApiTypes.STR, 
                location=OpenApiParameter.QUERY, 
                description='Username (exact match)',
                examples=[
                    OpenApiExample(
                        'johndoe',
                        value='johndoe'
                    )
                ]
            ),
            OpenApiParameter(
                name='balance_min', 
                type=OpenApiTypes.DECIMAL, 
                location=OpenApiParameter.QUERY, 
                description='Minimum balance',
                examples=[
                    OpenApiExample(
                        'Minimum $100',
                        value=100.00
                    )
                ]
            ),
            OpenApiParameter(
                name='balance_max', 
                type=OpenApiTypes.DECIMAL, 
                location=OpenApiParameter.QUERY, 
                description='Maximum balance',
                examples=[
                    OpenApiExample(
                        'Maximum $500',
                        value=500.00
                    )
                ]
            ),
            OpenApiParameter(
                name='created_at_after', 
                type=OpenApiTypes.DATETIME, 
                location=OpenApiParameter.QUERY, 
                description='Created at (start range)',
                examples=[
                    OpenApiExample(
                        'Created after 2024-01-01',
                        value='2024-01-01T00:00:00Z'
                    )
                ]
            ),
            OpenApiParameter(
                name='created_at_before', 
                type=OpenApiTypes.DATETIME, 
                location=OpenApiParameter.QUERY, 
                description='Created at (end range)',
                examples=[
                    OpenApiExample(
                        'Created before 2024-12-31',
                        value='2024-12-31T23:59:59Z'
                    )
                ]
            ),
        ],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

class TransactionViewSet(BaseServiceViewSet):
    """
    Read-only viewset for listing and retrieving transactions, with action processing.
    """

    serializer_class = TransactionSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = TransactionFilter
    pagination_class = TransactionPagination
    http_method_names = ['get', 'post']

    def get_queryset(self):
        """
        Retrieve transactions based on user role, including related_user.

        Returns:
            QuerySet: Filtered transactions (all for staff, user-related otherwise).
        """
        queryset = Transaction.objects.select_related('wallet', 'wallet__user', 'related_wallet', 'related_wallet__user').all().order_by('-created_at')
        if not self.request.user.is_staff:
            return queryset.filter(Q(wallet__user=self.request.user) | Q(related_wallet__user=self.request.user))
        return queryset

    @action(detail=False, methods=['post'], serializer_class=TransactionActionSerializer)
    def process_action(self, request):
        """
        Accept or reject a pending transaction.

        Args:
            request: HTTP request with action data (action, reference).

        Returns:
            Response: Success message or error details.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        action = serializer.validated_data['action']
        reference = serializer.validated_data['reference']

        sender_tx = self._get_transaction(reference, Transaction.TransactionTypes.DEBIT)
        recipient_tx = self._get_transaction(reference, Transaction.TransactionTypes.CREDIT)
        message = 'Transaction accepted' if action == 'accept' else 'Transaction rejected'
        self.transaction_service.execute(
            action=action,
            sender_transaction=sender_tx,
            recipient_transaction=recipient_tx,
            user=request.user
        )
        return Response({'message': message}, status=status.HTTP_200_OK)

    def _get_transaction(self, reference, transaction_type):
        """
        Retrieve a transaction by reference and type.

        Args:
            reference: Transaction reference string.
            transaction_type: Type of transaction (e.g., DEBIT, CREDIT).

        Returns:
            Transaction: Matching transaction object.

        Raises:
            CustomValidationError: If transaction is not found.
        """
        try:
            return Transaction.objects.get(reference=reference, transaction_type=transaction_type)
        except Transaction.DoesNotExist:
            raise CustomValidationError("Transaction not found or not yours")
    
    @extend_schema(
        parameters=[
            OpenApiParameter(
                name='sender',
                type=OpenApiTypes.STR, 
                location=OpenApiParameter.QUERY, 
                description='Sender username (exact match)',
                examples=[
                    OpenApiExample(
                        'Sender username',
                        value='johndoe'
                    )
                ]
            ),
            OpenApiParameter(
                name='recipient', 
                type=OpenApiTypes.STR, 
                location=OpenApiParameter.QUERY, 
                description='Recipient username (exact match)',
                examples=[
                    OpenApiExample(
                        'Recipient username',
                        value='janedoe'
                    )
                ]
            ),
            OpenApiParameter(
                name='involving_user', 
                type=OpenApiTypes.STR, 
                location=OpenApiParameter.QUERY, 
                description='Transactions involving user as sender or recipient',
                examples=[
                    OpenApiExample(
                        'Involving user',
                        value='johndoe'
                    )
                ]
            ),
            OpenApiParameter(
                name='amount_min', 
                type=OpenApiTypes.DECIMAL, 
                location=OpenApiParameter.QUERY, 
                description='Minimum amount',
                examples=[
                    OpenApiExample(
                        'Minimum amount',
                        value='10.00'
                    )
                ]
            ),
            OpenApiParameter(
                name='amount_max', 
                type=OpenApiTypes.DECIMAL, 
                location=OpenApiParameter.QUERY, 
                description='Maximum amount',
                examples=[
                    OpenApiExample(
                        'Maximum amount',
                        value='100.00'
                    )
                ]
            ),
            OpenApiParameter(
                name='transaction_type', 
                type=OpenApiTypes.STR, 
                location=OpenApiParameter.QUERY, 
                description='Transaction type',
                examples=[
                    OpenApiExample(
                        'Transaction type',
                        value='DEBIT'
                    )
                ]
            ),
            OpenApiParameter(
                name='funding_source', 
                type=OpenApiTypes.STR, 
                location=OpenApiParameter.QUERY, 
                description='Funding source',
                examples=[
                    OpenApiExample(
                        'Funding source',
                        value='BANK'
                    )
                ]
            ),
            OpenApiParameter(
                name='status', 
                type=OpenApiTypes.STR, 
                location=OpenApiParameter.QUERY, 
                description='Status of the transaction',
                examples=[
                    OpenApiExample(
                        'Status',
                        value='PENDING'
                    )
                ]
            ),
            OpenApiParameter(
                name='reference', 
                type=OpenApiTypes.STR, 
                location=OpenApiParameter.QUERY, 
                description='Partial or full reference text',
                examples=[
                    OpenApiExample(
                        'Reference',
                        value='12345'
                    )
                ]
            ),
            OpenApiParameter(
                name='created_at_after', 
                type=OpenApiTypes.DATETIME, 
                location=OpenApiParameter.QUERY, 
                description='Created at (start range)',
                examples=[
                    OpenApiExample(
                        'Created at after',
                        value='2023-01-01T00:00:00Z'
                    )
                ]
            ),
            OpenApiParameter(
                name='created_at_before', 
                type=OpenApiTypes.DATETIME, 
                location=OpenApiParameter.QUERY, 
                description='Created at (end range)',
                examples=[
                    OpenApiExample(
                        'Created at before',
                        value='2023-12-31T23:59:59Z'
                    )
                ]
            ),
            OpenApiParameter(
                name='expiry_time_after', 
                type=OpenApiTypes.DATETIME, 
                location=OpenApiParameter.QUERY, 
                description='Expiry time (start range)',
                examples=[
                    OpenApiExample(
                        'Expiry time after',
                        value='2023-01-01T00:00:00Z'
                    )
                ]
            ),
            OpenApiParameter(
                name='expiry_time_before', 
                type=OpenApiTypes.DATETIME, 
                location=OpenApiParameter.QUERY, 
                description='Expiry time (end range)',
                examples=[
                    OpenApiExample(
                        'Expiry time before',
                        value='2023-12-31T23:59:59Z'
                    )
                ]
            )
        ]
    )
    def list(self, request, *args, **kwargs):
        user_id = request.user.id
        page = request.query_params.get('page', '1')
        page_size = request.query_params.get('page_size', self.pagination_class.page_size)
        cache_key = f"transaction_list_{user_id}_page_{page}_size_{page_size}"

        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return Response(cached_data)

        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            data = self.get_paginated_response(serializer.data).data
        else:
            serializer = self.get_serializer(queryset, many=True)
            data = serializer.data

        cache.set(cache_key, data, timeout=CACHE_TIMEOUT)
        return Response(data)



class BaseWebhookView(GenericAPIView):
    throttle_scope = 'wallet'

    def __init__(self, wallet_service=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        factory = WalletServiceFactory()
        self.wallet_service = wallet_service or factory.create_wallet_service()

@method_decorator(csrf_exempt, name='dispatch')
class PaysendWebhookView(BaseWebhookView, IdempotencyMixin):
    permission_classes = [AllowAny]
    serializer_class = PaysendWebhookSerializer

    def post(self, request):
        """
        Process Paysend webhook payload for completed transactions.

        Args:
            request: HTTP request with webhook payload.

        Returns:
            Response: Processing status or error details.
        """
        def process_paysend_webhook(request, *args, **kwargs):
            if request.META.get('REMOTE_ADDR') not in settings.IP_WHITELIST:
                return Response({'detail': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)
            if not self._verify_signature(request.body, request.headers.get('X-Paysend-Signature', '')):
                return Response({'detail': 'Invalid signature'}, status=status.HTTP_401_UNAUTHORIZED)

            payload = self._parse_payload(request.body)
            if payload.get('status') != 'COMPLETED':
                return Response({'status': 'ignored'}, status=status.HTTP_200_OK)

            wallet, amount, reference = self._extract_transaction_data(payload)
            transaction = self._process_deposit(wallet, amount, reference)
            return Response(
                {'status': 'processed', 'transaction_id': transaction.id},
                status=status.HTTP_200_OK
            )

        return self.enforce_idempotency(request, process_paysend_webhook)

    def _verify_signature(self, payload, signature):
        secret = settings.PAYSEND_WEBHOOK_SECRET.encode()
        expected = hmac.new(secret, msg=payload, digestmod=hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    def _parse_payload(self, body):
        try:
            return json.loads(body.decode('utf-8'))
        except (ValueError, KeyError) as e:
            raise CustomValidationError(f"Invalid payload: {str(e)}")

    def _extract_transaction_data(self, payload):
        try:
            phone_number = payload['recipient']['phone_number']
            amount = Decimal(payload['recipient']['amount'])
            reference = f"Paysend: {payload['transactionId']}"
            wallet = get_object_or_404(Wallet, user__phone_number=phone_number)
            return wallet, amount, reference
        except (KeyError, ValueError) as e:
            raise CustomValidationError(f"Invalid transaction data: {str(e)}")

    def _process_deposit(self, wallet, amount, reference):
        return self.wallet_service.process(
            process_type='deposit',
            wallet=wallet,
            amount=amount,
            funding_source=Transaction.FundingSource.PAYSEND,
            reference=reference
        )


@method_decorator(csrf_exempt, name='dispatch')
class CashOutVerifyView(BaseWebhookView, IdempotencyMixin):
    permission_classes = [AllowAny]
    serializer_class = CashOutVerifySerializer

    def post(self, request):
        """
        Verify a cash-out request using phone number and withdrawal code.

        Args:
            request: HTTP request with verification data (phone_number, withdrawal_code).

        Returns:
            Response: Approval details or error message.
        """
        def process_cashout_verify(request, *args, **kwargs):
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            phone_number = serializer.validated_data['phone_number']
            withdrawal_code = serializer.validated_data['withdrawal_code']

            if request.META.get('REMOTE_ADDR') not in settings.IP_WHITELIST:
                return Response({'detail': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)

            try:
                transaction = self.wallet_service.verify_cash_out(phone_number, withdrawal_code)
                return Response(
                    {
                        'status': 'approved',
                        'amount': str(abs(transaction.amount)),
                        'transaction_id': transaction.id
                    },
                    status=status.HTTP_200_OK
                )
            except CustomValidationError as e:
                return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
            except Transaction.DoesNotExist:
                return Response(
                    {'detail': 'Invalid withdrawal code or phone number'},
                    status=status.HTTP_404_NOT_FOUND
                )

        return self.enforce_idempotency(request, process_cashout_verify)