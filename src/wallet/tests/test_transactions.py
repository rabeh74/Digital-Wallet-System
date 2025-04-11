# wallet/tests/test_transactions.py
from django.urls import reverse
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
import json
import hmac
import hashlib
from django.conf import settings
from wallet.models import Wallet, Transaction

User = get_user_model()


class TransactionViewSetTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            email='testuser@example.com'
        )
        self.wallet = self.user.wallet
        self.deposit = Transaction.objects.create(
            user=self.user,
            amount=Decimal('50.00'),
            transaction_type=Transaction.TransactionTypes.DEPOSIT,
            funding_source=Transaction.FundingSource.PAYSEND,
            reference='Initial deposit',
            status=Transaction.Status.COMPLETED
        )
        self.withdrawal = Transaction.objects.create(
            user=self.user,
            amount=Decimal('-20.00'),
            transaction_type=Transaction.TransactionTypes.WITHDRAWAL,
            funding_source=Transaction.FundingSource.BLF_ATM,
            reference='Cash withdrawal',
            status=Transaction.Status.COMPLETED
        )
        self.transactions_url = reverse('wallet:transaction-list')
        self.client.force_authenticate(user=self.user)

    def test_list_transactions(self):
        """Test listing transactions"""
        response = self.client.get(self.transactions_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)
        deposit_data = next(t for t in response.data['results'] if t['id'] == self.deposit.id)
        self.assertEqual(deposit_data['transaction_type'], Transaction.TransactionTypes.DEPOSIT)
        self.assertEqual(Decimal(deposit_data['amount']), Decimal('50.00'))

    def test_retrieve_transaction(self):
        """Test retrieving a single transaction"""
        url = reverse('wallet:transaction-detail', kwargs={'pk': self.deposit.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], self.deposit.id)
        self.assertEqual(response.data['reference'], 'Initial deposit')


class PaysendWebhookTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
            phone_number='96170123456'
        )

        self.wallet = self.user.wallet
        self.wallet.balance = Decimal('100.00')
        self.wallet.save()

        self.webhook_url = reverse('wallet:paysend-webhook')
        settings.PAYSEND_WEBHOOK_SECRET = 'test_webhook_secret'

    def get_signature(self, payload):
        """Generate valid HMAC signature for payload"""
        secret = settings.PAYSEND_WEBHOOK_SECRET.encode()
        return hmac.new(secret, msg=payload, digestmod=hashlib.sha256).hexdigest()

    def test_successful_webhook_processing(self):
        """Test successful webhook processing"""
        payload = {
            'transactionId': 'pay_123456789',
            'status': 'COMPLETED',
            'recipient': {'phone_number': '96170123456', 'amount': '60.00'}
        }
        payload_bytes = json.dumps(payload).encode('utf-8')
        signature = self.get_signature(payload_bytes)

        response = self.client.post(
            self.webhook_url,
            data=payload_bytes,
            content_type='application/json',
            HTTP_X_PAYSEND_SIGNATURE=signature
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'processed')
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal('160.00'))

    def test_invalid_signature(self):
        """Test webhook with invalid signature"""
        payload = {
            'transactionId': 'pay_123456789',
            'status': 'COMPLETED',
            'recipient': {'phone_number': '96170123456', 'amount': '60.00'}
        }
        payload_bytes = json.dumps(payload).encode('utf-8')

        response = self.client.post(
            self.webhook_url,
            data=payload_bytes,
            content_type='application/json',
            HTTP_X_PAYSEND_SIGNATURE='invalid_signature'
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data['detail'], 'Invalid signature')

    def test_duplicate_transaction(self):
        """Test idempotency with duplicate transaction ID"""
        payload = {
            'transactionId': 'pay_123456789',
            'status': 'COMPLETED',
            'recipient': {'phone_number': '96170123456', 'amount': '60.00'}
        }
        payload_bytes = json.dumps(payload).encode('utf-8')
        signature = self.get_signature(payload_bytes)

        self.client.post(
            self.webhook_url,
            data=payload_bytes,
            content_type='application/json',
            HTTP_X_PAYSEND_SIGNATURE=signature
        )
        response = self.client.post(
            self.webhook_url,
            data=payload_bytes,
            content_type='application/json',
            HTTP_X_PAYSEND_SIGNATURE=signature
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'already_processed')
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal('160.00'))


class CashOutTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser',
            phone_number='+96112345678',
            email='testuser@example.com',
            password='testpass123'
        )

        self.wallet = self.user.wallet
        self.wallet.balance = Decimal('1000.00')
        self.wallet.save()

        self.url_request = reverse('wallet:wallet-cash-out-request')
        self.url_verify = reverse('wallet:cash-out-verify')

    def test_cash_out_request_success(self):
        """Test successful cash-out request"""
        self.client.force_authenticate(user=self.user)
        response = self.client.post(self.url_request, {'amount': '100.00'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('withdrawal_code', response.data)
        self.assertEqual(Decimal(response.data['amount']), Decimal('100.00'))

        transaction = Transaction.objects.get(user=self.user)
        self.assertEqual(transaction.status, Transaction.Status.PENDING)
        self.assertEqual(transaction.amount, Decimal('-100.00'))
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal('1000.00'))

    def test_cash_out_verify_success(self):
        """Test successful cash-out verification"""
        self.client.force_authenticate(user=self.user)
        response = self.client.post(self.url_request, {'amount': '100.00'}, format='json')
        withdrawal_code = response.data['withdrawal_code']

        response = self.client.post(self.url_verify, {
            'phone_number': '+96112345678',
            'withdrawal_code': withdrawal_code
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'approved')
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal('900.00'))

    def test_cash_out_verify_expired_code(self):
        """Test verification with expired code"""
        self.client.force_authenticate(user=self.user)
        response = self.client.post(self.url_request, {'amount': '100.00'}, format='json')
        withdrawal_code = response.data['withdrawal_code']

        transaction = Transaction.objects.get(user=self.user)
        transaction.expiry_time = timezone.now() - timedelta(minutes=1)
        transaction.save()

        response = self.client.post(self.url_verify, {
            'phone_number': '+96112345678',
            'withdrawal_code': withdrawal_code
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['detail'], 'Withdrawal code has expired')

    def test_cash_out_verify_insufficient_funds(self):
        """Test verification with insufficient funds"""
        self.user.phone_number = '+96112345678'
        self.user.save()

        self.client.force_authenticate(user=self.user)
        response = self.client.post(self.url_request, {'amount': '1000.00'}, format='json')
        withdrawal_code = response.data['withdrawal_code']

        self.wallet.balance = Decimal('500.00')
        self.wallet.save()

        response = self.client.post(self.url_verify, {
            'phone_number': '+96112345678',
            'withdrawal_code': withdrawal_code
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['detail'], 'Insufficient funds')