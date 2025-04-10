# wallet/tests/test_transactions.py
import uuid
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
from wallet.models import Transaction , Wallet
from django.core.cache import cache
from django.test import TestCase
from django.db.models.signals import post_save
from wallet.signals import invalidate_transaction_cache


User = get_user_model()


class TransactionViewSetTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            email='testuser@example.com',
            phone_number='96170123456'
        )
        self.wallet = self.user.wallet
        self.deposit = Transaction.objects.create(
            wallet=self.user.wallet,
            amount=Decimal('50.00'),
            transaction_type=Transaction.TransactionTypes.DEPOSIT,
            funding_source=Transaction.FundingSource.PAYSEND,
            reference='Initial deposit',
            status=Transaction.Status.COMPLETED
        )
        self.withdrawal = Transaction.objects.create(
            wallet=self.user.wallet,
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
    
    def test_caching_and_pagination(self):
        """Test caching and pagination"""
        Transaction.objects.all().delete()
        for i in range(15):
            Transaction.objects.create(
                wallet=self.user.wallet,
                amount=Decimal('10.00'),
                transaction_type=Transaction.TransactionTypes.DEPOSIT,
                funding_source=Transaction.FundingSource.PAYSEND,
                reference=f'Transaction {i}',
                status=Transaction.Status.COMPLETED
            )
        with self.assertNumQueries(2):
            response = self.client.get(self.transactions_url, {'page': 1})
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(len(response.data['results']), 10)
            self.assertEqual(response.data['count'], 15)

        # Check cache
        cache_key = f"transaction_list_{self.user.id}_page_1_size_10"
        cached_data = cache.get(cache_key)
        self.assertIsNotNone(cached_data)
        self.assertEqual(cached_data['count'], 15)

        # Page 1: uses cache
        with self.assertNumQueries(0):
            response = self.client.get(self.transactions_url, {'page': 1})
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data, cached_data)

        # Page 2: hits DB
        response = self.client.get(self.transactions_url, {'page': 2})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 5)  # Remaining items
        cache_key_page2 = f"transaction_list_{self.user.id}_page_2_size_10"
        self.assertIsNotNone(cache.get(cache_key_page2))
    
    def test_try_not_allowed_method(self):
        response = self.client.put(self.transactions_url)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        response = self.client.delete(self.transactions_url)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

       


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
        settings.IP_WHITELIST = ['127.0.0.1']

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
            HTTP_X_PAYSEND_SIGNATURE=signature,
            HTTP_Idempotency_Key = str(uuid.uuid4())
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
            HTTP_X_PAYSEND_SIGNATURE='invalid_signature',
            HTTP_Idempotency_Key = str(uuid.uuid4())
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

        cur_uuid = str(uuid.uuid4())
        self.client.post(
            self.webhook_url,
            data=payload_bytes,
            content_type='application/json',
            HTTP_X_PAYSEND_SIGNATURE=signature,
            HTTP_Idempotency_Key = cur_uuid
        )
        response = self.client.post(
            self.webhook_url,
            data=payload_bytes,
            content_type='application/json',
            HTTP_X_PAYSEND_SIGNATURE=signature,
            HTTP_Idempotency_Key = cur_uuid
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'processed')
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal('160.00'))
    
    def test_ip_not_whitelisted(self):
        """Test unauthorized webhook request due to IP not whitelisted"""
        payload = {
            'transactionId': 'pay_123456789',
            'status': 'COMPLETED',
            'recipient': {'phone_number': '96170123456', 'amount': '60.00'}
        }
        payload_bytes = json.dumps(payload).encode('utf-8')
        signature = self.get_signature(payload_bytes)

        settings.IP_WHITELIST = []
        response = self.client.post(
            self.webhook_url,
            data=payload_bytes,
            content_type='application/json',
            HTTP_X_PAYSEND_SIGNATURE=signature,
            HTTP_Idempotency_Key = str(uuid.uuid4())
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data['detail'], 'Unauthorized')


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
        response = self.client.post(self.url_request, {'amount': '100.00'}, format='json' , HTTP_Idempotency_Key = str(uuid.uuid4()))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('withdrawal_code', response.data)
        self.assertEqual(Decimal(response.data['amount']), Decimal('100.00'))

        transaction = Transaction.objects.get(wallet=self.user.wallet)
        self.assertEqual(transaction.status, Transaction.Status.PENDING)
        self.assertEqual(transaction.amount, Decimal('100.00'))
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal('1000.00'))

    def test_cash_out_verify_success(self):
        """Test successful cash-out verification"""
        self.client.force_authenticate(user=self.user)
        response = self.client.post(self.url_request, {'amount': '100.00'}, format='json' , HTTP_Idempotency_Key = str(uuid.uuid4()))
        
        withdrawal_code = response.data['withdrawal_code']

        response = self.client.post(self.url_verify, {
            'phone_number': '+96112345678',
            'withdrawal_code': withdrawal_code
        }, format='json' , HTTP_Idempotency_Key = str(uuid.uuid4()))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'approved')
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal('900.00'))

    def test_cash_out_verify_expired_code(self):
        """Test verification with expired code"""
        self.client.force_authenticate(user=self.user)
        response = self.client.post(self.url_request, {'amount': '100.00'}, format='json' , HTTP_Idempotency_Key = str(uuid.uuid4()))
        withdrawal_code = response.data['withdrawal_code']

        transaction = Transaction.objects.get(wallet=self.user.wallet)
        transaction.expiry_time = timezone.now() - timedelta(minutes=1)
        transaction.save()

        response = self.client.post(self.url_verify, {
            'phone_number': '+96112345678',
            'withdrawal_code': withdrawal_code
        }, format='json' , HTTP_Idempotency_Key = str(uuid.uuid4()))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['detail'], 'Withdrawal code has expired')

    def test_cash_out_verify_insufficient_funds(self):
        """Test verification with insufficient funds"""
        self.user.phone_number = '+96112345678'
        self.user.save()

        self.client.force_authenticate(user=self.user)
        response = self.client.post(self.url_request, {'amount': '1000.00'}, format='json' , HTTP_Idempotency_Key = str(uuid.uuid4()))
        withdrawal_code = response.data['withdrawal_code']

        self.wallet.balance = Decimal('500.00')
        self.wallet.save()

        response = self.client.post(self.url_verify, {
            'phone_number': '+96112345678',
            'withdrawal_code': withdrawal_code
        }, format='json' , HTTP_Idempotency_Key = str(uuid.uuid4()))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['detail'], 'Insufficient funds')
    


class TransactionCacheInvalidationTests(TestCase):
    def setUp(self):
        # Create test users and wallets
        self.user1 = User.objects.create_user(username='user1', email='user1@example.com' , phone_number='+96112345678',)
        self.user2 = User.objects.create_user(username='user2', email='user2@example.com' , phone_number='+9611234532678',)

        self.wallet1 = self.user1.wallet
        self.wallet2 = self.user2.wallet
        self.wallet1.balance = Decimal('1000.00')
        self.wallet2.balance = Decimal('500.00')
        self.wallet1.save()
        self.wallet2.save()

        # Populate cache with sample data
        self.cache_key1 = "transaction_list_{}_page_1_size_10".format(self.user1.id)
        self.cache_key2 = "transaction_list_{}_page_1_size_10".format(self.user2.id)
        cache.set(self.cache_key1, {"transactions": ["test_data_1"]}, timeout=3600)
        cache.set(self.cache_key2, {"transactions": ["test_data_2"]}, timeout=3600)

        # Ensure signal is connected (should be by default via apps.py)
        post_save.connect(invalidate_transaction_cache, sender=Transaction)

    def tearDown(self):
        # Clear cache and disconnect signal for clean slate
        cache.clear()
        post_save.disconnect(invalidate_transaction_cache, sender=Transaction)

    def test_cache_invalidation_on_create_single_user(self):
        """Test cache invalidation for a transaction with only wallet.user."""
        # Verify cache exists initially
        self.assertIsNotNone(cache.get(self.cache_key1))
        self.assertIsNotNone(cache.get(self.cache_key2))

        # Create a transaction
        Transaction.objects.create(
            wallet=self.wallet1,
            amount=Decimal('50.00'),
            transaction_type=Transaction.TransactionTypes.DEPOSIT,
            status=Transaction.Status.COMPLETED,
            reference='TEST_DEPOSIT_001'
        )

        self.assertIsNone(cache.get(self.cache_key1))
        self.assertIsNotNone(cache.get(self.cache_key2))