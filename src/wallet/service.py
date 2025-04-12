"""
Service layer for wallet and transaction operations.

This module implements repository, strategy, and command patterns for modularity
and consistency, with logging for key operations and errors.
"""

from abc import ABC, abstractmethod
import uuid
from datetime import timedelta
from django.db import transaction as db_transaction
from django.utils import timezone
import logging

from .models import Wallet, Transaction
from .notifications import NotificationService
from .exceptions import CustomValidationError
from .utils import set_logging_context

# Configuration constants
CASH_OUT_EXPIRY_MINUTES = 30

logger = logging.getLogger('wallet.service')

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
        set_logging_context(user_id=user.id)
        wallet = Wallet.objects.filter(user=user).first()
        logger.debug(
            f"Wallet {'found' if wallet else 'not found'}",
            extra={'user_id': user.id ,'wallet_id': wallet.id if wallet else None}
        )
        return wallet

    def get_or_create(self, user):
        """
        Get or create a wallet for a user.

        Args:
            user: User instance to associate with the wallet.

        Returns:
            tuple: (Wallet object, created boolean).

        Raises:
            CustomValidationError: If wallet creation fails.
        """
        set_logging_context(user_id=user.id)
        try:
            wallet, created = Wallet.objects.get_or_create(user=user)
            return wallet, created
        except Exception as e:
            logger.error(
                f"Failed to get or create wallet: {str(e)}",
                extra={'user_id': user.id}
            )
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
        set_logging_context(user_id=wallet.user.id)
        logger.info(
            f"Updating wallet balance by {amount}",
            extra={'user_id': wallet.user.id, 'wallet_id': wallet.id ,'amount': amount}
        )
        try:
            wallet.balance += amount
            wallet.save(update_fields=['balance'])
            logger.debug(
                f"Wallet balance updated to {wallet.balance}",
                extra={'user_id': wallet.user.id, 'wallet_id': wallet.id ,'amount': amount}
            )
            return wallet
        except Exception as e:
            logger.error(
                f"Failed to update wallet balance: {str(e)}",
                extra={'user_id': wallet.user.id, 'wallet_id': wallet.id ,'amount': amount}
            )
            raise


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
        user_id = kwargs.get('wallet').user.id if kwargs.get('wallet') else 'N/A'
        reference = kwargs.get('reference', 'N/A')
        set_logging_context(user_id=user_id, transaction_ref=reference)
        try:
            transaction = Transaction.objects.create(**kwargs)
            logger.info(
                "Transaction created",
                extra={'user_id': user_id, 'transaction_ref': transaction.reference ,'wallet_id': kwargs['wallet'].id ,'amount': kwargs.get('amount')}
            )
            return transaction
        except Exception as e:
            logger.error(
                f"Failed to create transaction: {str(e)}",
                extra={'user_id': user_id, 'transaction_ref': reference ,'wallet_id': kwargs['wallet'].id ,'amount': kwargs.get('amount')}
            )
            raise

    def get_by_reference_and_wallet(self, reference, wallet):
        """
        Retrieve a transaction by reference and wallet.

        Args:
            reference: Transaction reference string.
            wallet: Wallet object to filter by.

        Returns:
            Transaction: Transaction object or None if not found.
        """
             
        transaction = Transaction.objects.filter(reference=reference, wallet=wallet).first()
        return transaction

    def get_by_id(self, transaction_id):
        """
        Retrieve a transaction by ID.

        Args:
            transaction_id: ID of the transaction.

        Returns:
            Transaction: Transaction object.

        Raises:
            CustomValidationError: If transaction not found.
        """
        
        try:
            transaction = Transaction.objects.get(id=transaction_id)
            return transaction
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
        transaction = Transaction.objects.select_for_update().filter(
            wallet__user__phone_number=phone_number,
            reference__endswith=withdrawal_code,
            status=Transaction.Status.PENDING
        ).first()
        return transaction

    def update_status(self, transaction, status):
        """
        Update the status of a transaction.

        Args:
            transaction: Transaction object to update.
            status: New status value.

        Returns:
            Transaction: Updated transaction object.
        """
        user_id = transaction.wallet.user.id if transaction.wallet else 'N/A'
        
        try:
            transaction.status = status
            transaction.save(update_fields=['status'])
            return transaction
        except Exception as e:
            logger.error(
                f"Failed to update transaction status: {str(e)}",
                extra={'user_id': user_id, 'transaction_ref': transaction.reference ,'wallet_id': transaction.wallet.id ,'amount': transaction.amount}
            )
            raise


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
        reference = f"DEPOSIT-{uuid.uuid4().hex[:8]}"
        user_id = kwargs['wallet'].user.id
        set_logging_context(user_id=user_id, transaction_ref=reference)
        logger.info(
            f"Processing deposit of {kwargs['amount']}",
            extra={'user_id': user_id, 'transaction_ref': reference ,'wallet_id': kwargs['wallet'].id ,'amount': kwargs.get('amount')}
        )
        try:
            with db_transaction.atomic():
                self.wallet_repository.update_balance(kwargs['wallet'], kwargs['amount'])
                transaction = self._create_transaction(
                    kwargs['wallet'], kwargs['amount'], kwargs['funding_source'], reference
                )
            logger.info(
                "Deposit processed successfully",
                extra={'user_id': user_id, 'transaction_ref': reference ,'wallet_id': kwargs['wallet'].id ,'amount': kwargs.get('amount')}
            )
            self.notification_service.send_transaction_notification(
                kwargs['wallet'].user.email, transaction, 'deposit'
            )
            return transaction
        except Exception as e:
            logger.error(
                f"Deposit failed: {str(e)}",
                extra={'user_id': user_id, 'transaction_ref': reference ,'wallet_id': kwargs['wallet'].id ,'amount': kwargs.get('amount')}
            )
            raise

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
        set_logging_context(user_id=wallet.user.id, transaction_ref=reference)
        transaction = self.transaction_repository.create(
            wallet=wallet,
            amount=amount,
            transaction_type=Transaction.TransactionTypes.DEPOSIT,
            funding_source=funding_source,
            reference=reference,
            status=Transaction.Status.COMPLETED
        )
        logger.debug(
            "Deposit transaction created",
            extra={'user_id': wallet.user.id, 'transaction_ref': reference ,'wallet_id': wallet.id ,'amount': amount}
        )
        return transaction


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
        reference = f"WITHDRAWAL-{uuid.uuid4().hex[:8]}"
        user_id = kwargs['wallet'].user.id
        set_logging_context(user_id=user_id, transaction_ref=reference)
        logger.info(
            f"Processing withdrawal of {kwargs['amount']}",
            extra={'user_id': user_id, 'transaction_ref': reference ,'wallet_id': kwargs['wallet'].id ,'amount': kwargs.get('amount')}
        )
        try:
            with db_transaction.atomic():
                self.wallet_repository.update_balance(kwargs['wallet'], -kwargs['amount'])
                transaction = self._create_transaction(
                    kwargs['wallet'], kwargs['amount'], kwargs['funding_source'], reference
                )
            logger.info(
                "Withdrawal processed successfully",
                extra={'user_id': user_id, 'transaction_ref': reference ,'wallet_id': kwargs['wallet'].id ,'amount': kwargs.get('amount')}
            )
            self.notification_service.send_transaction_notification(
                kwargs['wallet'].user.email, transaction, 'withdrawal'
            )
            return transaction
        except Exception as e:
            logger.error(
                f"Withdrawal failed: {str(e)}",
                extra={'user_id': user_id, 'transaction_ref': reference ,'wallet_id': kwargs['wallet'].id ,'amount': kwargs.get('amount')}
            )
            raise

    def _create_transaction(self, wallet, amount, funding_source, reference):
        """
        Create a withdrawal transaction.

        Args:
            wallet: Wallet initiating the withdrawal.
            amount: Decimal amount.
            funding_source: Funding source enum.
            reference: Transaction reference string.

        Returns:
            Transaction: Created transaction object.
        """
        set_logging_context(user_id=wallet.user.id, transaction_ref=reference)
        logger.debug(
            "Creating withdrawal transaction",
            extra={'user_id': wallet.user.id, 'transaction_ref': reference ,'wallet_id': wallet.id ,'amount': amount}
        )
        transaction = self.transaction_repository.create(
            wallet=wallet,
            amount=-amount,
            transaction_type=Transaction.TransactionTypes.WITHDRAWAL,
            funding_source=funding_source,
            reference=reference,
            status=Transaction.Status.COMPLETED
        )
        logger.debug(
            "Withdrawal transaction created",
            extra={'user_id': wallet.user.id, 'transaction_ref': reference ,'wallet_id': wallet.id ,'amount': amount}
        )
        return transaction


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
        reference = f"TRANSFER-{uuid.uuid4().hex[:8]}"
        user_id = kwargs['wallet'].user.id
        set_logging_context(user_id=user_id, transaction_ref=reference)
        logger.info(
            f"Processing transfer of {kwargs['amount']} to recipient wallet",
            extra={'user_id': user_id, 'transaction_ref': reference}
        )
        try:
            with db_transaction.atomic():
                sender_transaction = self._process_sender_transaction(
                    kwargs['wallet'], kwargs['recipient_wallet'], kwargs['amount'], reference
                )
                recipient_transaction = self._process_recipient_transaction(
                    kwargs['wallet'], kwargs['recipient_wallet'], kwargs['amount'], reference
                )
            self._send_notifications(
                kwargs['wallet'].user, kwargs['recipient_wallet'].user, sender_transaction, recipient_transaction
            )
            logger.info(
                "Transfer processed successfully",
                extra={'user_id': user_id, 'transaction_ref': reference ,'wallet_id': kwargs['wallet'].id ,'amount': kwargs.get('amount')}
            )
            return reference
        except Exception as e:
            logger.error(
                f"Transfer failed: {str(e)}",
                extra={'user_id': user_id, 'transaction_ref': reference ,'wallet_id': kwargs['wallet'].id ,'amount': kwargs.get('amount')}
            )
            raise

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
        set_logging_context(user_id=wallet.user.id, transaction_ref=reference)
        logger.debug(
            "Processing sender transaction",
            extra={'user_id': wallet.user.id, 'transaction_ref': reference ,'wallet_id': wallet.id ,'amount': amount}
        )
        self.wallet_repository.update_balance(wallet, -amount)
        transaction = self.transaction_repository.create(
            wallet=wallet,
            related_wallet=recipient_wallet,
            amount=amount,
            transaction_type=Transaction.TransactionTypes.TRANSFER_OUT,
            funding_source=Transaction.FundingSource.INTERNAL,
            status=Transaction.Status.PENDING,
            reference=reference
        )
        logger.debug(
            "Sender transaction created",
            extra={'user_id': wallet.user.id, 'transaction_ref': reference ,'wallet_id': wallet.id ,'amount': amount}
        )
        return transaction

    def _process_recipient_transaction(self, wallet, recipient_wallet, amount, reference):
        """
        Process the recipient's side of the transfer.

        Args:
            wallet: Sender wallet instance.
            recipient_wallet: Recipient wallet instance.
            amount: Decimal amount to transfer.
            reference: Transaction reference string.

        Returns:
            Transaction: Recipient's transaction object.
        """
        set_logging_context(user_id=recipient_wallet.user.id, transaction_ref=reference)
        logger.debug(
            "Processing recipient transaction",
            extra={'user_id': recipient_wallet.user.id, 'transaction_ref': reference ,'wallet_id': recipient_wallet.id ,'amount': amount}
        )
        transaction = self.transaction_repository.create(
            wallet=recipient_wallet,
            related_wallet=wallet,
            amount=amount,
            transaction_type=Transaction.TransactionTypes.TRANSFER_IN,
            funding_source=Transaction.FundingSource.INTERNAL,
            status=Transaction.Status.PENDING,
            reference=reference
        )
        logger.debug(
            "Recipient transaction created",
            extra={'user_id': recipient_wallet.user.id, 'transaction_ref': reference ,'wallet_id': recipient_wallet.id ,'amount': amount}
        )
        return transaction

    def _send_notifications(self, sender_user, recipient_user, sender_transaction, recipient_transaction):
        """
        Send notifications for the transfer.

        Args:
            sender_user: Sender user instance.
            recipient_user: Recipient user instance.
            sender_transaction: Sender's transaction object.
            recipient_transaction: Recipient's transaction object.
        """
        set_logging_context(transaction_ref=sender_transaction.reference)
        logger.debug(
            "Sending transfer notifications",
            extra={'user_id': sender_user.id, 'transaction_ref': sender_transaction.reference ,'wallet_id': sender_transaction.wallet.id ,'amount': sender_transaction.amount}
        )
        self.notification_service.send_transaction_notification(
            sender_user.email, sender_transaction, 'transfer_sent'
        )
        self.notification_service.send_transaction_notification(
            recipient_user.email, recipient_transaction, 'transfer_received'
        )
        logger.debug(
            "Transfer notifications sent",
            extra={'user_id': sender_user.id, 'transaction_ref': sender_transaction.reference ,'wallet_id': sender_transaction.wallet.id ,'amount': sender_transaction.amount}
        )


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
            CustomValidationError: If transaction is invalid or not owned by user.
        """
        reference = kwargs['sender_transaction'].reference
        user_id = kwargs['recipient_transaction'].wallet.user.id
        set_logging_context(user_id=user_id, transaction_ref=reference)
        logger.info(
            "Executing accept command",
            extra={'user_id': user_id, 'transaction_ref': reference ,'wallet_id': kwargs['sender_transaction'].wallet.id ,'amount': kwargs['sender_transaction'].amount}
        )
        try:
            with db_transaction.atomic():
                self._credit_recipient(kwargs['recipient_transaction'])
                self._complete_transactions(kwargs['sender_transaction'], kwargs['recipient_transaction'])
                self._notify_users(kwargs['sender_transaction'], kwargs['recipient_transaction'])
            logger.info(
                "Accept command executed successfully",
                extra={'user_id': user_id, 'transaction_ref': reference ,'wallet_id': kwargs['sender_transaction'].wallet.id ,'amount': kwargs['sender_transaction'].amount}
            )
        except Exception as e:
            logger.error(
                f"Accept command failed: {str(e)}",
                extra={'user_id': user_id, 'transaction_ref': reference ,'wallet_id': kwargs['sender_transaction'].wallet.id ,'amount': kwargs['sender_transaction'].amount}
            )
            raise

    def _credit_recipient(self, recipient_transaction):
        """
        Credit the recipient's wallet and update status.

        Args:
            recipient_transaction: Recipient's transaction object.
        """
        user_id = recipient_transaction.wallet.user.id
        set_logging_context(user_id=user_id, transaction_ref=recipient_transaction.reference)
        logger.debug(
            "Crediting recipient wallet",
            extra={'user_id': user_id, 'transaction_ref': recipient_transaction.reference ,'wallet_id': recipient_transaction.wallet.id ,'amount': recipient_transaction.amount}
        )
        self.wallet_repository.update_balance(recipient_transaction.wallet, abs(recipient_transaction.amount))
        self.transaction_repository.update_status(recipient_transaction, Transaction.Status.ACCEPTED)
        logger.debug(
            "Recipient wallet credited",
            extra={'user_id': user_id, 'transaction_ref': recipient_transaction.reference ,'wallet_id': recipient_transaction.wallet.id ,'amount': recipient_transaction.amount}
        )

    def _complete_transactions(self, sender_transaction, recipient_transaction):
        """
        Mark both transactions as completed.

        Args:
            sender_transaction: Sender's transaction object.
            recipient_transaction: Recipient's transaction object.
        """
        user_id = recipient_transaction.wallet.user.id
        set_logging_context(user_id=user_id, transaction_ref=sender_transaction.reference)
        logger.debug(
            "Completing transactions",
            extra={'user_id': user_id, 'transaction_ref': sender_transaction.reference}
        )
        self.transaction_repository.update_status(sender_transaction, Transaction.Status.COMPLETED)
        self.transaction_repository.update_status(recipient_transaction, Transaction.Status.COMPLETED)
        logger.debug(
            "Transactions completed",
            extra={'user_id': user_id, 'transaction_ref': sender_transaction.reference ,'wallet_id': sender_transaction.wallet.id ,'amount': sender_transaction.amount}
        )

    def _notify_users(self, sender_transaction, recipient_transaction):
        """
        Notify users of the accepted transfer.

        Args:
            sender_transaction: Sender's transaction object.
            recipient_transaction: Recipient's transaction object.
        """
        user_id = recipient_transaction.wallet.user.id
        set_logging_context(user_id=user_id, transaction_ref=sender_transaction.reference)
        logger.debug(
            "Notifying users of accepted transfer",
            extra={'user_id': user_id, 'transaction_ref': sender_transaction.reference ,'wallet_id': sender_transaction.wallet.id ,'amount': sender_transaction.amount}
        )
        self.notification_service.send_transaction_notification(
            sender_transaction.wallet.user.email, sender_transaction, 'transfer_accepted'
        )
        self.notification_service.send_transaction_notification(
            recipient_transaction.wallet.user.email, recipient_transaction, 'transfer_accepted'
        )
        logger.debug(
            "Users notified of accepted transfer",
            extra={'user_id': user_id, 'transaction_ref': sender_transaction.reference ,'wallet_id': sender_transaction.wallet.id ,'amount': sender_transaction.amount}
        )


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
        reference = kwargs['sender_transaction'].reference
        user_id = kwargs['recipient_transaction'].wallet.user.id
        set_logging_context(user_id=user_id, transaction_ref=reference)
        logger.info(
            "Executing reject command",
            extra={'user_id': user_id, 'transaction_ref': reference}
        )
        try:
            with db_transaction.atomic():
                self._refund_sender(kwargs['sender_transaction'])
                self._reject_transactions(kwargs['sender_transaction'], kwargs['recipient_transaction'])
                self._notify_users(kwargs['sender_transaction'], kwargs['recipient_transaction'])
            logger.info(
                "Reject command executed successfully",
                extra={'user_id': user_id, 'transaction_ref': reference}
            )
        except Exception as e:
            logger.error(
                f"Reject command failed: {str(e)}",
                extra={'user_id': user_id, 'transaction_ref': reference}
            )
            raise

    def _refund_sender(self, sender_transaction):
        """
        Refund the sender's wallet and update status.

        Args:
            sender_transaction: Sender's transaction object.
        """
        user_id = sender_transaction.wallet.user.id
        set_logging_context(user_id=user_id, transaction_ref=sender_transaction.reference)
        logger.debug(
            "Refunding sender wallet",
            extra={'user_id': user_id, 'transaction_ref': sender_transaction.reference}
        )
        self.wallet_repository.update_balance(sender_transaction.wallet, abs(sender_transaction.amount))
        self.transaction_repository.update_status(sender_transaction, Transaction.Status.REJECTED)
        logger.debug(
            "Sender wallet refunded",
            extra={'user_id': user_id, 'transaction_ref': sender_transaction.reference}
        )

    def _reject_transactions(self, sender_transaction, recipient_transaction):
        """
        Mark both transactions as rejected.

        Args:
            sender_transaction: Sender's transaction object.
            recipient_transaction: Recipient's transaction object.
        """
        user_id = recipient_transaction.wallet.user.id
        set_logging_context(user_id=user_id, transaction_ref=sender_transaction.reference)
        logger.debug(
            "Rejecting transactions",
            extra={'user_id': user_id, 'transaction_ref': sender_transaction.reference}
        )
        self.transaction_repository.update_status(sender_transaction, Transaction.Status.REJECTED)
        self.transaction_repository.update_status(recipient_transaction, Transaction.Status.REJECTED)
        logger.debug(
            "Transactions rejected",
            extra={'user_id': user_id, 'transaction_ref': sender_transaction.reference}
        )

    def _notify_users(self, sender_transaction, recipient_transaction):
        """
        Notify users of the rejected transfer.

        Args:
            sender_transaction: Sender's transaction object.
            recipient_transaction: Recipient's transaction object.
        """
        user_id = recipient_transaction.wallet.user.id
        set_logging_context(user_id=user_id, transaction_ref=sender_transaction.reference)
        logger.debug(
            "Notifying users of rejected transfer",
            extra={'user_id': user_id, 'transaction_ref': sender_transaction.reference}
        )
        self.notification_service.send_transaction_notification(
            sender_transaction.wallet.user.email, sender_transaction, 'transfer_rejected'
        )
        self.notification_service.send_transaction_notification(
            recipient_transaction.wallet.user.email, recipient_transaction, 'transfer_rejected'
        )
        logger.debug(
            "Users notified of rejected transfer",
            extra={'user_id': user_id, 'transaction_ref': sender_transaction.reference}
        )


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
        set_logging_context(user_id=user.id)
        try:
            wallet, created = self.wallet_repository.get_or_create(user)
            logger.info(
                f"Wallet {'created' if created else 'retrieved'}",
                extra={'user_id': user.id, 'wallet_id': wallet.id}
            )
            return wallet
        except CustomValidationError as e:
            logger.error(f"Failed to create wallet: {str(e)}", extra={'user_id': user.id})
            raise

    def process(self, **kwargs):
        """
        Process a transaction using the appropriate strategy.

        Args:
            **kwargs: Transaction details (process_type, user, amount, etc.).

        Returns:
            Transaction or str: Transaction object or reference, depending on strategy.
        """
        process_type = kwargs.get('process_type')
        user_id = kwargs.get('wallet').user.id if kwargs.get('wallet') else 'N/A'
        reference = kwargs.get('reference', 'N/A')
        set_logging_context(user_id=user_id, transaction_ref=reference)
        logger.info(
            f"Processing {process_type} transaction",
            extra={'user_id': user_id, 'transaction_ref': reference}
        )
        try:
            result = self.strategies[process_type].process(**kwargs)
            logger.info(
                f"{process_type.capitalize()} transaction processed successfully",
                extra={
                    'user_id': user_id,
                    'transaction_ref': result if isinstance(result, str) else result.reference
                }
            )
            return result
        except Exception as e:
            logger.error(
                f"Failed to process {process_type} transaction: {str(e)}",
                extra={'user_id': user_id, 'transaction_ref': reference}
            )
            raise

    def request_cash_out(self, wallet, amount):
        """
        Request a cash-out with a withdrawal code.

        Args:
            wallet: Wallet object to withdraw from.
            amount: Decimal amount to withdraw.

        Returns:
            str: Withdrawal code.
        """
        set_logging_context(user_id=wallet.user.id)
        logger.info(
            f"Requesting cash-out of {amount} for wallet",
            extra={'user_id': wallet.user.id, 'wallet_id': wallet.id}
        )
        try:
            withdrawal_code = str(uuid.uuid4().hex[:8]).upper()
            transaction = self.transaction_repository.create(
                wallet=wallet,
                amount=amount,
                transaction_type=Transaction.TransactionTypes.WITHDRAWAL,
                funding_source=Transaction.FundingSource.BLF_ATM,
                reference=f"BLF-ATM-{withdrawal_code}",
                status=Transaction.Status.PENDING,
                expiry_time=timezone.now() + timedelta(minutes=CASH_OUT_EXPIRY_MINUTES)
            )
            logger.info(
                "Cash-out requested successfully",
                extra={'user_id': wallet.user.id, 'transaction_ref': transaction.reference}
            )
            self.notification_service.send_transaction_notification(
                wallet.user.email, transaction, 'cash_out_requested'
            )
            return withdrawal_code
        except Exception as e:
            logger.error(
                f"Failed to request cash-out: {str(e)}",
                extra={'user_id': wallet.user.id}
            )
            raise

    def verify_cash_out(self, phone_number, withdrawal_code):
        """
        Verify and complete a cash-out request.

        Args:
            phone_number: User's phone number.
            withdrawal_code: Withdrawal code to verify.

        Returns:
            Transaction: Completed transaction object.

        Raises:
            CustomValidationError: If code or phone number is invalid.
            ExpiredTransactionError: If code has expired.
            InsufficientFundsError: If wallet balance is insufficient.
        """
        reference = f"BLF-ATM-{withdrawal_code}"
        set_logging_context(transaction_ref=reference)
        logger.info(
            f"Verifying cash-out with code {withdrawal_code} for phone {phone_number}",
            extra={'transaction_ref': reference}
        )
        try:
            with db_transaction.atomic():
                transaction = self.transaction_repository.get_by_withdrawal_code(phone_number, withdrawal_code)
                if not transaction:
                    logger.error(
                        "Invalid withdrawal code or phone number",
                        extra={'transaction_ref': reference}
                    )
                    raise CustomValidationError("Invalid withdrawal code or phone number")
                wallet = transaction.wallet
                self.wallet_repository.update_balance(wallet, -transaction.amount)
                self.transaction_repository.update_status(transaction, Transaction.Status.COMPLETED)
                logger.info(
                    "Cash-out verified successfully",
                    extra={'user_id': wallet.user.id, 'transaction_ref': transaction.reference}
                )
                self.notification_service.send_transaction_notification(
                    wallet.user.email, transaction, 'cash_out_verified'
                )
                return transaction
        except CustomValidationError as e:
            logger.error(
                f"Cash-out verification failed: {str(e)}",
                extra={'transaction_ref': reference}
            )
            raise
        except Exception as e:
            logger.error(
                f"Unexpected error during cash-out verification: {str(e)}",
                extra={'transaction_ref': reference}
            )
            raise


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
        set_logging_context(transaction_ref=transaction_id)
        logger.info(
            "Retrieving transaction",
            extra={'transaction_ref': transaction_id}
        )
        try:
            transaction = self.transaction_repository.get_by_id(transaction_id)
            logger.info(
                "Transaction retrieved",
                extra={
                    'user_id': transaction.wallet.user.id if transaction.wallet else 'N/A',
                    'transaction_ref': transaction_id
                }
            )
            return transaction
        except CustomValidationError as e:
            logger.error(
                f"Failed to retrieve transaction: {str(e)}",
                extra={'transaction_ref': transaction_id}
            )
            raise

    def execute(self, **kwargs):
        """
        Execute a transaction command (accept or reject).

        Args:
            **kwargs: Command arguments (action, sender_transaction, recipient_transaction, user).
        """
        action = kwargs['action']
        reference = kwargs['sender_transaction'].reference
        user_id = kwargs['recipient_transaction'].wallet.user.id
        set_logging_context(user_id=user_id, transaction_ref=reference)
        logger.info(
            f"Executing {action} command",
            extra={'user_id': user_id, 'transaction_ref': reference}
        )
        try:
            self.commands[action].execute(**kwargs)
            logger.info(
                f"{action.capitalize()} command executed successfully",
                extra={'user_id': user_id, 'transaction_ref': reference}
            )
        except Exception as e:
            logger.error(
                f"Failed to execute {action} command: {str(e)}",
                extra={'user_id': user_id, 'transaction_ref': reference}
            )
            raise


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
        service = WalletService(wallet_repo, transaction_repo, notification_service, strategies)
        return service

    @staticmethod
    def create_transaction_service():
        """
        Create a TransactionService instance.

        Returns:
            TransactionService: Configured transaction service instance.
        """
        wallet_repo, transaction_repo, notification_service = WalletServiceFactory._create_repositories()
        service = TransactionService(wallet_repo, transaction_repo, notification_service)
        return service