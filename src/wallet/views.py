# wallet/views.py
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import Wallet
from .serializers import WalletSerializer
from user.permissions import IsOwner
from .service import WalletService

class WalletViewSet(viewsets.ModelViewSet):
    serializer_class = WalletSerializer
    permission_classes = [IsAuthenticated , IsOwner]
    http_method_names = ['get', 'post', 'head', 'options']  # Only allow create and read

    def get_queryset(self):
        """Get wallet for authenticated user or all wallets for admin"""
        base_queryset = Wallet.objects.all()
        if not self._is_admin():
            return base_queryset.filter(user=self.request.user)
        return base_queryset

    def _is_admin(self):
        return self.request.user.is_staff

    def create(self, request, *args, **kwargs):
        """Create wallet for authenticated user (if doesn't exist)"""
        if hasattr(request.user, 'wallet'):
            return Response(
                {'error': 'Wallet already exists'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        wallet = WalletService.create_wallet(request.user)
        serializer = self.get_serializer(wallet)
        return Response(serializer.data, status=status.HTTP_201_CREATED)