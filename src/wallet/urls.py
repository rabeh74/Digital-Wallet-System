# wallet/urls.py
from rest_framework.routers import DefaultRouter
from .views import WalletViewSet

router = DefaultRouter()
router.register(r'wallets', WalletViewSet, basename='wallet')

urlpatterns = router.urls