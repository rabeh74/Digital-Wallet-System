from django.urls import reverse

from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken


def create_user(**params):
    return get_user_model().objects.create_user(**params)

def create_superuser(**params):
    return get_user_model().objects.create_superuser(**params)

user_params = {
    'email':'test@email.com',
    'password':'testpass',
    'phone_number':'1234567890',
}


class UserPublicAPITests(APITestCase):
    def setUp(self):
        self.user_params = {
            'email': 'test@email.com',
            'password1':'test54*&^%&pass',
            'password2':'test54*&^%&pass',
        }
    
    def test_create_user(self):
        url = reverse('user:create_user')
        data = self.user_params
        response = self.client.post(url, data)
        data = response.data['data']
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = get_user_model().objects.get(email=data['email'])
        self.assertTrue(user.check_password(self.user_params['password1']))
        self.assertNotIn('password1', data)
        self.assertEqual(data['email'], self.user_params['email'])

class UserAPITests(APITestCase):
    def setUp(self):
        self.user_params = {
            'email': 'test@email.com',
            'password':'testpass',
            'phone_number':'1234567890',
        }
        self.user = create_user(**self.user_params)
        self.login_url = reverse('user:token_obtain_pair')
        self.refresh_url = reverse('user:token_refresh')
        self.user_update_url = reverse('user:update_user', args=[self.user.id])

    def test_successful_login(self):
        """
        Ensure a user can log in and get access/refresh tokens.
        """
        data = self.user_params
        response = self.client.post(self.login_url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_invalid_credentials(self):
        """
        Ensure login fails with invalid credentials.
        """
        data = {
            "email": self.user.email,
            "password": "wrongpassword"
        }
        response = self.client.post(self.login_url, data)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertNotIn("access", response.data)
        self.assertNotIn("refresh", response.data)

    def test_token_refresh(self):
        """
        Ensure the refresh token generates a new access token.
        """
        refresh = RefreshToken.for_user(self.user)
        data = {
            "refresh": str(refresh)
        }
        response = self.client.post(self.refresh_url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
    
    def test_user_update(self):
        """
        Ensure a user can update their details.
        """
        new_data = {
            "phone_number": "1234567890" ,
            "password1": "test%$1232p",
            "password2": "test%$1232p",
        }

        self.client.force_authenticate(user=self.user)
        url = self.user_update_url
        response = self.client.put(url, new_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.phone_number, new_data["phone_number"])
        self.assertTrue(self.user.check_password(new_data["password1"]))
        self.assertNotIn("password", response.data)
        self.assertEqual("test@email.com", self.user.email)
    
    def test_user_update_invalid_password(self):
        """
        Ensure a user cannot update with invalid password.
        """
        new_data = {
            "phone_number": "1234567890" ,
            "password1": "newpassword",
            "password2": "wrongpassword",
        }
        self.client.force_authenticate(user=self.user)
        url = self.user_update_url
        response = self.client.put(url, new_data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertEqual(self.user.phone_number, self.user_params["phone_number"])
        self.assertTrue(self.user.check_password(self.user_params["password"]))
        self.assertNotIn("password", response.data)
        self.assertEqual("test@email.com", self.user.email)
    
    def test_user_list(self):
        """
        Ensure an admin can list all users.
        """
        admin_user = create_superuser(email='test1@example.com', password='testpass123')
        create_user(email='test2@example.com', password='testpass123')
        create_user(email='test3@example.com', password='testpass123')
        create_user(email='test4@example.com', password='testpass123')

        self.client.force_authenticate(user=admin_user)
        url = reverse('user:list_users')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 5)
    
    def test_user_update_another_user(self):
        """
        Ensure a user cannot update another user's details.
        """
        another_user = create_user(email='test5@example.com', password='testpass123')
        self.client.force_authenticate(user=another_user)
        response = self.client.put(self.user_update_url, {"email": "another_user@email.com"})
        print(response.data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    