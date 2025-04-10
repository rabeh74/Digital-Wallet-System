# wallet/tests/test_wallet_core.py
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model
from decimal import Decimal
from wallet.models import Wallet, Transaction

User = get_user_model()


class WalletAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='user@example.com',
            password='testpass123',
            username='user'
        )
        self.client.force_authenticate(user=self.user)
        self.wallet_url = reverse('wallet:wallet-list')

    def test_create_wallet(self):
        """Test creating a wallet"""
        response = self.client.post(self.wallet_url)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['user']['id'], self.user.id)
        self.assertEqual(Decimal(response.data['balance']), Decimal('0.00'))

    def test_create_existing_wallet(self):
        """Test cannot create wallet if already exists"""
        self.client.post(self.wallet_url)
        response = self.client.post(self.wallet_url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['detail'], 'Wallet already exists')

    def test_retrieve_wallet(self):
        """Test retrieving wallet details"""
        self.client.post(self.wallet_url)
        response = self.client.get(self.wallet_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['user']['id'], self.user.id)

    def test_unauthenticated_access(self):
        """Test that unauthenticated users can't access wallets"""
        self.client.logout()
        response = self.client.get(self.wallet_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_use_not_allowed_methods(self):
        """Test that non-GET/POST requests are not allowed"""
        response = self.client.put(self.wallet_url)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        response = self.client.delete(self.wallet_url)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_admin_access(self):
        """Test that admin users can access all wallets"""
        admin_user = User.objects.create_superuser(
            email='admin@example.com',
            password='adminpass123',
            username='admin'
        )
        user1 = User.objects.create_user(
            email='user1@example.com',
            password='user1pass123',
            username='user1'
        )
        user2 = User.objects.create_user(
            email='user2@example.com',
            password='user2pass123',
            username='user2'
        )
        Wallet.objects.create(user=user1)
        Wallet.objects.create(user=user2)

        self.client.force_authenticate(user=admin_user)
        response = self.client.get(self.wallet_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)


class WalletTransferTests(APITestCase):
    def setUp(self):
        self.sender = User.objects.create_user(
            username='sender',
            password='testpass123',
            email='sender@example.com'
        )
        self.recipient = User.objects.create_user(
            username='recipient',
            password='testpass123',
            email='recipient@example.com'
        )
        self.sender_wallet = Wallet.objects.create(user=self.sender, balance=Decimal('100.00'))
        self.recipient_wallet = Wallet.objects.create(user=self.recipient, balance=Decimal('0.00'))
        self.transfer_url = reverse('wallet:wallet-transfer')
        self.transaction_action_url = reverse('wallet:transaction-process-action')
        self.client.force_authenticate(user=self.sender)

    def test_successful_transfer_and_accept(self):
        """Test successful transfer initiation and acceptance"""
        response = self.client.post(self.transfer_url, {
            'recipient_username': 'recipient',
            'amount': '50.00',
            'reference': 'Test transfer'
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['message'], 'Transfer initiated successfully')
        reference = response.data['reference']

        self.sender_wallet.refresh_from_db()
        self.recipient_wallet.refresh_from_db()
        self.assertEqual(self.sender_wallet.balance, Decimal('50.00'))
        self.assertEqual(self.recipient_wallet.balance, Decimal('0.00'))

        sender_transaction = Transaction.objects.get(reference=reference, transaction_type=Transaction.TransactionTypes.DEBIT)
        recipient_transaction = Transaction.objects.get(reference=reference, transaction_type=Transaction.TransactionTypes.CREDIT)
        self.assertEqual(sender_transaction.status, Transaction.Status.PENDING)
        self.assertEqual(recipient_transaction.status, Transaction.Status.PENDING)

        self.client.force_authenticate(user=self.recipient)
        response = self.client.post(self.transaction_action_url, {
            'action': 'accept',
            'reference': reference
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['message'], 'Transaction accepted')

        self.sender_wallet.refresh_from_db()
        self.recipient_wallet.refresh_from_db()
        sender_transaction.refresh_from_db()
        recipient_transaction.refresh_from_db()
        self.assertEqual(self.sender_wallet.balance, Decimal('50.00'))
        self.assertEqual(self.recipient_wallet.balance, Decimal('50.00'))
        self.assertEqual(sender_transaction.status, Transaction.Status.COMPLETED)
        self.assertEqual(recipient_transaction.status, Transaction.Status.COMPLETED)

    def test_successful_transfer_and_reject(self):
        """Test successful transfer initiation and rejection"""
        response = self.client.post(self.transfer_url, {
            'recipient_username': 'recipient',
            'amount': '50.00',
            'reference': 'Test transfer'
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        reference = response.data['reference']

        self.sender_wallet.refresh_from_db()
        self.assertEqual(self.sender_wallet.balance, Decimal('50.00'))

        sender_transaction = Transaction.objects.get(reference=reference, transaction_type=Transaction.TransactionTypes.DEBIT)
        recipient_transaction = Transaction.objects.get(reference=reference, transaction_type=Transaction.TransactionTypes.CREDIT)

        self.client.force_authenticate(user=self.recipient)
        response = self.client.post(self.transaction_action_url, {
            'action': 'reject',
            'reference': reference
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['message'], 'Transaction rejected')

        self.sender_wallet.refresh_from_db()
        self.recipient_wallet.refresh_from_db()
        sender_transaction.refresh_from_db()
        recipient_transaction.refresh_from_db()
        self.assertEqual(self.sender_wallet.balance, Decimal('100.00'))
        self.assertEqual(self.recipient_wallet.balance, Decimal('0.00'))
        self.assertEqual(sender_transaction.status, Transaction.Status.REJECTED)
        self.assertEqual(recipient_transaction.status, Transaction.Status.REJECTED)

    def test_insufficient_funds(self):
        """Test transfer with insufficient balance"""
        response = self.client.post(self.transfer_url, {
            'recipient_username': 'recipient',
            'amount': '150.00'
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['detail'], 'Insufficient funds')
        self.sender_wallet.refresh_from_db()
        self.assertEqual(self.sender_wallet.balance, Decimal('100.00'))

    def test_self_transfer(self):
        """Test attempt to transfer to self"""
        response = self.client.post(self.transfer_url, {
            'recipient_username': 'sender',
            'amount': '10.00'
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['detail'], 'Cannot transfer to yourself')

    def test_invalid_recipient(self):
        """Test transfer to non-existent user"""
        response = self.client.post(self.transfer_url, {
            'recipient_username': 'nonexistent',
            'amount': '10.00'
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['detail'], 'User nonexistent does not exist')

    def test_invalid_amount(self):
        """Test transfer with invalid amount"""
        response = self.client.post(self.transfer_url, {
            'recipient_username': 'recipient',
            'amount': '0.00'
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['detail'], 'Amount must be positive')