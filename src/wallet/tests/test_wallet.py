# wallet/tests.py
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model
from wallet.models import Wallet

User = get_user_model()

class WalletAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='user@example.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)
        self.wallet_url = reverse('wallet-list')

    def test_create_wallet(self):
        """Test creating a wallet"""
        response = self.client.post(self.wallet_url)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['user'], self.user.id)
        self.assertEqual(response.data['balance'], '0.00')

    def test_create_existing_wallet(self):
        """Test cannot create wallet if already exists"""
        self.client.post(self.wallet_url)
        response = self.client.post(self.wallet_url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)

    def test_retrieve_wallet(self):
        """Test retrieving wallet details"""
        self.client.post(self.wallet_url)
        response = self.client.get(self.wallet_url)
        print(response.data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)  
        self.assertEqual(response.data[0]['user'], self.user.id)


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
        """Test that admin users can access wallets"""
        admin_user = User.objects.create_superuser(
            email='admin@example.com',
            password='adminpass123'
        )
        user1 = User.objects.create_user(
            email='user1@example.com',
            password='user1pass123'
        )
        user2 = User.objects.create_user(
            email='user2@example.com',
            password='user2pass123'
        )
        Wallet.objects.create(user=user1)
        Wallet.objects.create(user=user2)


        self.client.force_authenticate(user=admin_user)
        response = self.client.get(self.wallet_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)  
    
    def test_create_wallet_twice(self):
        """Test that creating wallet twice is not allowed"""
        self.client.post(self.wallet_url)
        response = self.client.post(self.wallet_url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
        self.assertEqual(response.data['error'], 'Wallet already exists')
    
        