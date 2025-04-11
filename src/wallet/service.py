# wallet/service.py
"""
Service layer for wallet and transaction operations, implementing repository,
strategy, and command patterns for modularity and consistency.
"""

from abc import ABC, abstractmethod
import uuid
from datetime import timedelta
from django.db import transaction as db_transaction
from django.utils import timezone

from .models import Wallet, Transaction
from .notifications import NotificationService
from .exceptions import CustomValidationError
# Configuration constants
CASH_OUT_EXPIRY_MINUTES = 30


class IWalletRepository(ABC):
    """Repository interface for wallet operations."""

    @abstractmethod
    def get_by_user(self, user):
        """Retrieve a wallet by user."""

    @abstractmethod
    def get_or_create(self, user):
        """Get or create a wallet for a user."""

    @abstractmethod
    def update_balance(self, wallet, amount):
        """Update the wallet balance with a given amount."""


class ITransactionRepository(ABC):
    """Repository interface for transaction operations."""

    @abstractmethod
    def create(self, **kwargs):
        """Create a new transaction."""

    @abstractmethod
    def get_by_reference_and_wallet(self, reference, wallet):
        """Retrieve a transaction by reference and wallet."""

    @abstractmethod
    def get_by_id(self, transaction_id):
        """Retrieve a transaction by ID."""

    @abstractmethod
    def get_by_withdrawal_code(self, phone_number, withdrawal_code):
        """Retrieve a transaction by phone number and withdrawal code."""

    @abstractmethod
    def update_status(self, transaction, status):
        """Update the status of a transaction."""


class WalletRepository(IWalletRepository):
    """Concrete implementation of wallet repository using Django ORM."""

    def get_by_user(self, user):
        """
        Retrieve a wallet by user.

        Args:
            user: User instance to fetch wallet for.

        Returns:
            Wallet: Wallet object or None if not found.
        """
        return Wallet.objects.filter(user=user).first()

    def get_or_create(self, user):
        """
        Get or create a wallet for a user.

        Args:
            user: User instance to associate with the wallet.

        Returns:
            tuple: (Wallet object, created boolean).

        Raises:
            ValidationError: If wallet creation fails.
        """
        try:
            return Wallet.objects.get_or_create(user=user)
        except Exception as e:
            raise CustomValidationError(f"Failed to get or create wallet: {str(e)}")

    def update_balance(self, wallet, amount):
        """
        Update the wallet balance with a given amount.

        Args:
            wallet: Wallet object to update.
            amount: Decimal amount to add (positive) or subtract (negative).

        Returns:
            Wallet: Updated wallet object.
        """
        wallet.balance += amount
        wallet.save(update_fields=['balance'])
        return wallet


class TransactionRepository(ITransactionRepository):
    """Concrete implementation of transaction repository using Django ORM."""

    def create(self, **kwargs):
        """
        Create a new transaction.

        Args:
            **kwargs: Transaction attributes (e.g., user, amount, reference).

        Returns:
            Transaction: Created transaction object.
        """
        return Transaction.objects.create(**kwargs)

    def get_by_reference_and_wallet(self, reference, wallet):
        """
        Retrieve a transaction by reference and wallet.

        Args:
            reference: Transaction reference string.
            wallet: Wallet object to filter by.

        Returns:
            Transaction: Transaction object or None if not found.
        """
        return Transaction.objects.filter(reference=reference, wallet=wallet).first()

    def get_by_id(self, transaction_id):
        """
        Retrieve a transaction by ID.

        Args:
            transaction_id: ID of the transaction.

        Returns:
            Transaction: Transaction object.

        """
        try:
            return Transaction.objects.get(id=transaction_id)
        except Transaction.DoesNotExist:
            raise CustomValidationError(f"Transaction {transaction_id} not found")

    def get_by_withdrawal_code(self, phone_number, withdrawal_code):
        """
        Retrieve a transaction by phone number and withdrawal code.

        Args:
            phone_number: User's phone number.
            withdrawal_code: Withdrawal code suffix of the reference.

        Returns:
            Transaction: Matching transaction or None if not found.
        """
        return Transaction.objects.select_for_update().filter(
            wallet__user__phone_number=phone_number,
            reference__endswith=withdrawal_code,
            status=Transaction.Status.PENDING
        ).first()

    def update_status(self, transaction, status):
        """
        Update the status of a transaction.

        Args:
            transaction: Transaction object to update.
            status: New     status value.

        Returns:
            Transaction: Updated transaction object.
        """
        transaction.status = status
        transaction.save(update_fields=['status'])
        return transaction


class TransactionStrategy(ABC):
    """Abstract base class for transaction processing strategies."""

    @abstractmethod
    def process(self, **kwargs):
        """Process a transaction based on the strategy."""


class DepositStrategy(TransactionStrategy):
    """Strategy for processing deposit transactions."""

    def __init__(self, wallet_repository, transaction_repository, notification_service):
        """
        Initialize the deposit strategy.

        Args:
            wallet_repository: IWalletRepository instance.
            transaction_repository: ITransactionRepository instance.
            notification_service: NotificationService instance.
        """
        self.wallet_repository = wallet_repository
        self.transaction_repository = transaction_repository
        self.notification_service = notification_service

    def process(self, **kwargs):
        """
        Process a deposit transaction.

        Args:
            **kwargs: Transaction details (user, amount, funding_source, reference).

        Returns:
            Transaction: Created transaction object.

        """
        with db_transaction.atomic():
            self.wallet_repository.update_balance(kwargs['wallet'], kwargs['amount'])
            transaction = self._create_transaction(kwargs['wallet'], kwargs['amount'], kwargs['funding_source'], kwargs['reference'])
        self.notification_service.send_transaction_notification(kwargs['wallet'].user.email, transaction, 'deposit')
        return transaction

    def _create_transaction(self, wallet, amount, funding_source, reference):
        """
        Create a deposit transaction.

        Args:
            wallet: Wallet receiving the deposit.
            amount: Decimal amount.
            funding_source: Funding source enum.
            reference: Transaction reference string.

        Returns:
            Transaction: Created transaction object.
        """
        return self.transaction_repository.create(
            wallet=wallet,
            amount=amount,
            transaction_type=Transaction.TransactionTypes.DEPOSIT,
            funding_source=funding_source,
            reference=reference,
            status=Transaction.Status.COMPLETED
        )


class WithdrawalStrategy(TransactionStrategy):
    """Strategy for processing withdrawal transactions."""

    def __init__(self, wallet_repository, transaction_repository, notification_service):
        """
        Initialize the withdrawal strategy.

        Args:
            wallet_repository: IWalletRepository instance.
            transaction_repository: ITransactionRepository instance.
            notification_service: NotificationService instance.
        """
        self.wallet_repository = wallet_repository
        self.transaction_repository = transaction_repository
        self.notification_service = notification_service

    def process(self, **kwargs):
        """
        Process a withdrawal transaction.

        Args:
            **kwargs: Transaction details (user, amount, funding_source, reference).

        Returns:
            Transaction: Created transaction object.
        """
        with db_transaction.atomic():
            self.wallet_repository.update_balance(kwargs['wallet'], -kwargs['amount'])
            transaction = self._create_transaction(kwargs['wallet'], kwargs['amount'], kwargs['funding_source'], kwargs['reference'])
        self.notification_service.send_transaction_notification(kwargs['wallet'].user.email, transaction, 'withdrawal')
        return transaction

    def _create_transaction(self, user, amount, funding_source, reference):
        """
        Create a withdrawal transaction.

        Args:
            user: User initiating the withdrawal.
            amount: Decimal amount.
            funding_source: Funding source enum.
            reference: Transaction reference string.

        Returns:
            Transaction: Created transaction object.
        """
        return self.transaction_repository.create(
            user=user,
            amount=-amount,
            transaction_type=Transaction.TransactionTypes.WITHDRAWAL,
            funding_source=funding_source,
            reference=reference,
            status=Transaction.Status.COMPLETED
        )


class TransferStrategy(TransactionStrategy):
    """Strategy for processing transfer transactions between wallets."""

    def __init__(self, wallet_repository, transaction_repository, notification_service):
        """
        Initialize the transfer strategy.

        Args:
            wallet_repository: IWalletRepository instance.
            transaction_repository: ITransactionRepository instance.
            notification_service: NotificationService instance.
        """
        self.wallet_repository = wallet_repository
        self.transaction_repository = transaction_repository
        self.notification_service = notification_service

    def process(self, **kwargs):
        """
        Process a transfer transaction.

        Args:
            **kwargs: Transfer details (user, recipient_user, amount, reference).

        Returns:
            str: Transaction reference.
        """
        reference = kwargs.get('reference') or f"TRANSFER-{uuid.uuid4().hex[:8]}"
        with db_transaction.atomic():
            sender_transaction = self._process_sender_transaction(kwargs['wallet'], kwargs['recipient_wallet'], kwargs['amount'], reference)
            recipient_transaction = self._process_recipient_transaction(kwargs['wallet'], kwargs['recipient_wallet'], kwargs['amount'], reference)
        self._send_notifications(kwargs['wallet'].user, kwargs['recipient_wallet'].user, sender_transaction, recipient_transaction)
        return reference

    def _process_sender_transaction(self, wallet, recipient_wallet, amount, reference):
        """
        Process the sender's side of the transfer.

        Args:
            wallet: Sender wallet instance.
            recipient_wallet: Recipient wallet instance.
            amount: Decimal amount to transfer.
            reference: Transaction reference string.

        Returns:
            Transaction: Sender's transaction object.
        """
        self.wallet_repository.update_balance(wallet, -amount)
        return self.transaction_repository.create(
            wallet=wallet,
            related_wallet=recipient_wallet,
            amount=-amount,
            transaction_type=Transaction.TransactionTypes.DEBIT,
            funding_source=Transaction.FundingSource.INTERNAL,
            status=Transaction.Status.PENDING,
            reference=reference
        )

    def _process_recipient_transaction(self, wallet, recipient_wallet, amount, reference):
        """
        Process the recipient's side of the transfer.

        Args:
            wallet: Sender wallet instance.
            recipient_user: Recipient user instance.
            amount: Decimal amount to transfer.
            reference: Transaction reference string.

        Returns:
            Transaction: Recipient's transaction object.
        """
        return self.transaction_repository.create(
            wallet=recipient_wallet,
            related_wallet=wallet,
            amount=amount,
            transaction_type=Transaction.TransactionTypes.CREDIT,
            funding_source=Transaction.FundingSource.INTERNAL,
            status=Transaction.Status.PENDING,
            reference=reference
        )

    def _send_notifications(self, sender_user, recipient_user, sender_transaction, recipient_transaction):
        """
        Send notifications for the transfer.

        Args:
            sender_user: Sender user instance.
            recipient_user: Recipient user instance.
            sender_transaction: Sender's transaction object.
            recipient_transaction: Recipient's transaction object.
        """
        self.notification_service.send_transaction_notification(sender_user.email, sender_transaction, 'transfer_sent')
        self.notification_service.send_transaction_notification(recipient_user.email, recipient_transaction, 'transfer_received')


class TransactionCommand(ABC):
    """Abstract base class for transaction commands."""

    @abstractmethod
    def execute(self, transaction, user):
        """Execute the transaction command."""


class AcceptTransactionCommand(TransactionCommand):
    """Command to accept a pending transfer transaction."""

    def __init__(self, wallet_repository, transaction_repository, notification_service):
        """
        Initialize the accept command.

        Args:
            wallet_repository: IWalletRepository instance.
            transaction_repository: ITransactionRepository instance.
            notification_service: NotificationService instance.
        """
        self.wallet_repository = wallet_repository
        self.transaction_repository = transaction_repository
        self.notification_service = notification_service

    def execute(self, **kwargs):
        """
        Execute the accept command for a transfer.

        Args:
            **kwargs: Command arguments (sender_transaction, recipient_transaction, user).

        Raises:
            InvalidTransactionError: If transaction is invalid or not owned by user.
        """
        with db_transaction.atomic():
            self._credit_recipient(kwargs['recipient_transaction'])
            self._complete_transactions(kwargs['sender_transaction'], kwargs['recipient_transaction'])
            self._notify_users(kwargs['sender_transaction'], kwargs['recipient_transaction'])


    def _credit_recipient(self, recipient_transaction):
        """
        Credit the recipient's wallet and update status.

        Args:
            recipient_transaction: Recipient's transaction object.
        """
        recipient_wallet = recipient_transaction.wallet
        self.wallet_repository.update_balance(recipient_wallet, abs(recipient_transaction.amount))
        self.transaction_repository.update_status(recipient_transaction, Transaction.Status.ACCEPTED)

    def _complete_transactions(self, sender_transaction, recipient_transaction):
        """
        Mark both transactions as completed.

        Args:
            sender_transaction: Sender's transaction object.
            recipient_transaction: Recipient's transaction object.
        """
        self.transaction_repository.update_status(sender_transaction, Transaction.Status.COMPLETED)
        self.transaction_repository.update_status(recipient_transaction, Transaction.Status.COMPLETED)

    def _notify_users(self, sender_transaction, recipient_transaction):
        """
        Notify users of the accepted transfer.

        Args:
            sender_transaction: Sender's transaction object.
            recipient_transaction: Recipient's transaction object.
        """
        self.notification_service.send_transaction_notification(sender_transaction.wallet.user.email, sender_transaction, 'transfer_accepted')
        self.notification_service.send_transaction_notification(recipient_transaction.wallet.user.email, recipient_transaction, 'transfer_accepted')


class RejectTransactionCommand(TransactionCommand):
    """Command to reject a pending transfer transaction."""

    def __init__(self, wallet_repository, transaction_repository, notification_service):
        """
        Initialize the reject command.

        Args:
            wallet_repository: IWalletRepository instance.
            transaction_repository: ITransactionRepository instance.
            notification_service: NotificationService instance.
        """
        self.wallet_repository = wallet_repository
        self.transaction_repository = transaction_repository
        self.notification_service = notification_service

    def execute(self, **kwargs):
        """
        Execute the reject command for a transfer.

        Args:
            **kwargs: Command arguments (sender_transaction, recipient_transaction, user).

        """
        with db_transaction.atomic():
            self._refund_sender(kwargs['sender_transaction'])
            self._reject_transactions(kwargs['sender_transaction'], kwargs['recipient_transaction'])
            self._notify_users(kwargs['sender_transaction'], kwargs['recipient_transaction'])


    def _refund_sender(self, sender_transaction):
        """
        Refund the sender's wallet and update status.

        Args:
            sender_transaction: Sender's transaction object.
        """
        sender_wallet = sender_transaction.wallet
        self.wallet_repository.update_balance(sender_wallet, abs(sender_transaction.amount))
        self.transaction_repository.update_status(sender_transaction, Transaction.Status.REJECTED)

    def _reject_transactions(self, sender_transaction, recipient_transaction):
        """
        Mark both transactions as rejected.

        Args:
            sender_transaction: Sender's transaction object.
            recipient_transaction: Recipient's transaction object.
        """
        self.transaction_repository.update_status(sender_transaction, Transaction.Status.REJECTED)
        self.transaction_repository.update_status(recipient_transaction, Transaction.Status.REJECTED)

    def _notify_users(self, sender_transaction, recipient_transaction):
        """
        Notify users of the rejected transfer.

        Args:
            sender_transaction: Sender's transaction object.
            recipient_transaction: Recipient's transaction object.
        """
        self.notification_service.send_transaction_notification(sender_transaction.wallet.user.email, sender_transaction, 'transfer_rejected')
        self.notification_service.send_transaction_notification(recipient_transaction.wallet.user.email, recipient_transaction, 'transfer_rejected')


class WalletService:
    """Service for managing wallet operations and transaction processing."""

    def __init__(self, wallet_repository, transaction_repository, notification_service, strategies=None):
        """
        Initialize the wallet service.

        Args:
            wallet_repository: IWalletRepository instance.
            transaction_repository: ITransactionRepository instance.
            notification_service: NotificationService instance.
            strategies: Optional dict of TransactionStrategy instances.
        """
        self.wallet_repository = wallet_repository
        self.transaction_repository = transaction_repository
        self.notification_service = notification_service
        self.strategies = strategies or {
            'deposit': DepositStrategy(wallet_repository, transaction_repository, notification_service),
            'withdrawal': WithdrawalStrategy(wallet_repository, transaction_repository, notification_service),
            'transfer': TransferStrategy(wallet_repository, transaction_repository, notification_service),
        }

    def create_wallet(self, user):
        """
        Create or retrieve a wallet for a user.

        Args:
            user: User instance to associate with the wallet.

        Returns:
            Wallet: Wallet object.
        """
        wallet, created = self.wallet_repository.get_or_create(user)
        return wallet

    def process(self, **kwargs):
        """
        Process a transaction using the appropriate strategy.

        Args:
            **kwargs: Transaction details (process_type, user, amount, etc.).

        Returns:
            Transaction or str: Transaction object or reference, depending on strategy.
        """
        return self.strategies[kwargs['process_type']].process(**kwargs)

    def request_cash_out(self, wallet, amount):
        """
        Request a cash-out with a withdrawal code.

        Args:
            wallet: Wallet object to withdraw from.
            amount: Decimal amount to withdraw.

        Returns:
            str: Withdrawal code.
        """

        withdrawal_code = str(uuid.uuid4().hex[:8]).upper()
        transaction = self.transaction_repository.create(
            wallet=wallet,
            amount=-amount,
            transaction_type=Transaction.TransactionTypes.WITHDRAWAL,
            funding_source=Transaction.FundingSource.BLF_ATM,
            reference=f"BLF-ATM-{withdrawal_code}",
            status=Transaction.Status.PENDING,
            expiry_time=timezone.now() + timedelta(minutes=CASH_OUT_EXPIRY_MINUTES)
        )
        self.notification_service.send_transaction_notification(wallet.user.email, transaction, 'cash_out_requested')
        return withdrawal_code

    def verify_cash_out(self, phone_number, withdrawal_code):
        """
        Verify and complete a cash-out request.

        Args:
            phone_number: User's phone number.
            withdrawal_code: Withdrawal code to verify.

        Returns:
            Transaction: Completed transaction object.

        Raises:
            InvalidTransactionError: If code or phone number is invalid.
            ExpiredTransactionError: If code has expired.
            InsufficientFundsError: If wallet balance is insufficient.
        """
        with db_transaction.atomic():
            transaction = self.transaction_repository.get_by_withdrawal_code(phone_number, withdrawal_code)
            if not transaction:
                raise InvalidTransactionError("Invalid withdrawal code or phone number")

            if timezone.now() > transaction.expiry_time:
                self.transaction_repository.update_status(transaction, Transaction.Status.EXPIRED)
                raise ExpiredTransactionError("Withdrawal code has expired")

            wallet = transaction.user.wallet
            if wallet.balance < abs(transaction.amount):
                self.transaction_repository.update_status(transaction, Transaction.Status.FAILED)
                raise InsufficientFundsError("Insufficient funds")

            self.wallet_repository.update_balance(wallet, transaction.amount)
            self.transaction_repository.update_status(transaction, Transaction.Status.COMPLETED)
            self.notification_service.send_transaction_notification(wallet.user.email, transaction, 'cash_out_verified')
            return transaction


class TransactionService:
    """Service for managing transaction state changes (accept/reject)."""

    def __init__(self, wallet_repository, transaction_repository, notification_service):
        """
        Initialize the transaction service.

        Args:
            wallet_repository: IWalletRepository instance.
            transaction_repository: ITransactionRepository instance.
            notification_service: NotificationService instance.
        """
        self.wallet_repository = wallet_repository
        self.transaction_repository = transaction_repository
        self.notification_service = notification_service
        self.commands = {
            'accept': AcceptTransactionCommand(wallet_repository, transaction_repository, notification_service),
            'reject': RejectTransactionCommand(wallet_repository, transaction_repository, notification_service),
        }

    def get_transaction(self, transaction_id):
        """
        Retrieve a transaction by ID.

        Args:
            transaction_id: ID of the transaction.

        Returns:
            Transaction: Transaction object.
        """
        return self.transaction_repository.get_by_id(transaction_id)

    def execute(self, **kwargs):
        """
        Execute a transaction command (accept or reject).

        Args:
            **kwargs: Command arguments (action, sender_transaction, recipient_transaction, user).
        """
        self.commands[kwargs['action']].execute(**kwargs)


class WalletServiceFactory:
    """Factory for creating wallet and transaction services."""

    @staticmethod
    def _create_repositories():
        """
        Create repository instances.

        Returns:
            tuple: (WalletRepository, TransactionRepository, NotificationService).
        """
        wallet_repository = WalletRepository()
        transaction_repository = TransactionRepository()
        notification_service = NotificationService()
        return wallet_repository, transaction_repository, notification_service

    @staticmethod
    def create_wallet_service(strategies=None):
        """
        Create a WalletService instance.

        Args:
            strategies: Optional dict of TransactionStrategy instances.

        Returns:
            WalletService: Configured wallet service instance.
        """
        wallet_repo, transaction_repo, notification_service = WalletServiceFactory._create_repositories()
        return WalletService(wallet_repo, transaction_repo, notification_service, strategies)

    @staticmethod
    def create_transaction_service():
        """
        Create a TransactionService instance.

        Returns:
            TransactionService: Configured transaction service instance.
        """
        wallet_repo, transaction_repo, notification_service = WalletServiceFactory._create_repositories()
        return TransactionService(wallet_repo, transaction_repo, notification_service)