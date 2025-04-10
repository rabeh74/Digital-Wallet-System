# wallet/tests/test_filters.py
from django.urls import reverse
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from wallet.models import Wallet, Transaction

User = get_user_model()


class WalletFilterTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user1 = User.objects.create_user(username='user1', password='pass123', email='user1@example.com')
        self.user2 = User.objects.create_user(username='user2', password='pass123', email='user2@example.com')
        self.wallet1 = Wallet.objects.create(user=self.user1, balance=Decimal('100.00'))
        self.wallet2 = Wallet.objects.create(user=self.user2, balance=Decimal('500.00'))
        self.url = reverse('wallet:wallet-list')
        self.admin = User.objects.create_superuser(username='admin', password='admin123', email='admin@example.com')
        self.client.force_authenticate(user=self.admin)

    def test_filter_by_user(self):
        response = self.client.get(self.url, {'user': self.user1.username}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['user']['username'], self.user1.username)

    def test_filter_by_balance_range(self):
        response = self.client.get(self.url, {'balance_min': '200', 'balance_max': '600'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['user']['username'], self.user2.username)

    def test_filter_by_created_at_range(self):
        self.wallet2.created_at = timezone.now() - timedelta(days=10)
        self.wallet2.save()
        response = self.client.get(self.url, {
            'created_at_after': (timezone.now() - timedelta(days=5)).isoformat(),
            'created_at_before': (timezone.now() + timedelta(days=5)).isoformat()
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['user']['username'], self.user1.username)

    def test_ordering_by_balance(self):
        response = self.client.get(self.url, {'ordering': 'balance'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
        self.assertEqual(response.data[0]['user']['username'], 'user1')
        self.assertEqual(response.data[1]['user']['username'], 'user2')

    def test_ordering_by_balance_descending(self):
        response = self.client.get(self.url, {'ordering': '-balance'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
        self.assertEqual(response.data[0]['user']['username'], 'user2')
        self.assertEqual(response.data[1]['user']['username'], 'user1')


class TransactionFilterTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user1 = User.objects.create_user(username='user1', password='pass123', email='user1@example.com')
        self.user2 = User.objects.create_user(username='user2', password='pass123', email='user2@example.com')
        self.wallet1 = Wallet.objects.create(user=self.user1, balance=Decimal('1000.00'))
        self.wallet2 = Wallet.objects.create(user=self.user2, balance=Decimal('500.00'))
        
        self.transaction1 = Transaction.objects.create(
            user=self.user1,
            related_user=self.user2,
            amount=Decimal('100.00'),
            transaction_type=Transaction.TransactionTypes.DEBIT,
            funding_source=Transaction.FundingSource.INTERNAL,
            reference='DEBIT-001',
            status=Transaction.Status.PENDING,
            expiry_time=timezone.now() + timedelta(hours=1)
        )
        self.transaction2 = Transaction.objects.create(
            user=self.user2,
            related_user=self.user1,
            amount=Decimal('50.00'),
            transaction_type=Transaction.TransactionTypes.DEPOSIT,
            funding_source=Transaction.FundingSource.PAYSEND,
            reference='DEP-001',
            status=Transaction.Status.COMPLETED,
            expiry_time=timezone.now() - timedelta(hours=1)
        )
        self.url = reverse('wallet:transaction-list')
        self.admin = User.objects.create_superuser(username='admin', password='admin123', email='admin@example.com')
        self.client.force_authenticate(user=self.admin)

    def test_filter_by_sender_user(self):
        response = self.client.get(self.url, {'user': 'user1'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['reference'], 'DEBIT-001')

    def test_filter_by_recipient_user(self):
        response = self.client.get(self.url, {'user': 'user2'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['reference'], 'DEP-001')

    def test_filter_by_amount_range(self):
        response = self.client.get(self.url, {'amount_min': '75', 'amount_max': '150'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['reference'], 'DEBIT-001')

    def test_filter_by_transaction_type(self):
        response = self.client.get(self.url, {'transaction_type': 'DEBIT'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['reference'], 'DEBIT-001')

    def test_filter_by_status(self):
        response = self.client.get(self.url, {'status': 'PENDING'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['reference'], 'DEBIT-001')

    def test_filter_by_reference(self):
        response = self.client.get(self.url, {'reference': 'DEBIT-001'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['reference'], 'DEBIT-001')

    def test_filter_by_created_at_range(self):
        self.transaction2.created_at = timezone.now() - timedelta(days=10)
        self.transaction2.save()
        response = self.client.get(self.url, {
            'created_at_after': (timezone.now() - timedelta(days=5)).isoformat(),
            'created_at_before': (timezone.now() + timedelta(days=5)).isoformat()
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['reference'], 'DEBIT-001')

    def test_filter_by_expiry_time_range(self):
        response = self.client.get(self.url, {
            'expiry_time_after': (timezone.now() - timedelta(hours=0)).isoformat(),
            'expiry_time_before': (timezone.now() + timedelta(hours=2)).isoformat()
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['reference'], 'DEBIT-001')

    def test_filter_by_involving_user(self):
        response = self.client.get(self.url, {'involving_user': 'user1'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
        references = {t['reference'] for t in response.data}
        self.assertEqual(references, {'DEBIT-001', 'DEP-001'})

    def test_ordering_by_amount(self):
        response = self.client.get(self.url, {'ordering': 'amount'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
        self.assertEqual(response.data[0]['reference'], 'DEP-001')
        self.assertEqual(response.data[1]['reference'], 'DEBIT-001')

    def test_ordering_by_created_at_descending(self):
        response = self.client.get(self.url, {'ordering': 'created_at'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
        self.assertEqual(response.data[0]['reference'], 'DEBIT-001')
        self.assertEqual(response.data[1]['reference'], 'DEP-001')