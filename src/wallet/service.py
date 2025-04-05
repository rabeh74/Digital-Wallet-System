from django.db import transaction as db_transaction
from .models import Wallet, Transaction

class WalletService:
    @staticmethod
    def create_wallet(user):
        """Create a new wallet for a user"""
        wallet, created = Wallet.objects.get_or_create(user=user)
        return wallet

    @staticmethod
    def add_funds(wallet, amount, funding_source, reference):
        """Add funds to a wallet"""
        if amount <= 0:
            raise ValueError("Amount must be positive")
        
        with db_transaction.atomic():
            wallet.balance += amount
            wallet.save()
            
            transaction = Transaction.objects.create(
                wallet=wallet,
                amount=amount,
                transaction_type=Transaction.TRANSACTION_TYPE.DEPOSIT,
                funding_source=funding_source,
                reference=reference,
                status='COMPLETED'
            )
            
        return transaction

    @staticmethod
    def transfer_funds(sender_wallet, recipient_wallet, amount):
        """Transfer funds between wallets"""
        if sender_wallet.balance < amount:
            raise ValueError("Insufficient funds")
        
        with db_transaction.atomic():
            sender_wallet.balance -= amount
            sender_wallet.save()
            
            recipient_wallet.balance += amount
            recipient_wallet.save()
            
            # Create transaction records
            Transaction.objects.create(
                wallet=sender_wallet,
                amount=amount,
                transaction_type=Transaction.TRANSACTION_TYPE.TRANSFER,
                funding_source=Transaction.FUNDING_SOURCE.PEER,
                reference=f"Transfer to {recipient_wallet.user.first_name} {recipient_wallet.user.last_name}",
                recipient=recipient_wallet,
                status='COMPLETED'
            )
            
            Transaction.objects.create(
                wallet=recipient_wallet,
                amount=amount,
                transaction_type=Transaction.TRANSACTION_TYPE.DEPOSIT,
                funding_source=Transaction.FUNDING_SOURCE.PEER,
                reference=f"Transfer from {sender_wallet.user.first_name} {sender_wallet.user.last_name}",
                status='COMPLETED'
            )