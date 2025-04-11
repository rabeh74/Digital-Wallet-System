from rest_framework.routers import DefaultRouter
from .views import WalletViewSet , TransactionViewSet , PaysendWebhookView , CashOutVerifyView
from django.urls import include , path

app_name = 'wallet'

router = DefaultRouter()
router.register(r'wallets', WalletViewSet, basename='wallet')
router.register(r'transactions', TransactionViewSet, basename='transaction')


urlpatterns = [
    path('', include(router.urls)),
    path('paysend/webhook/', PaysendWebhookView.as_view(), name='paysend-webhook'),
    path('cash-out-verify/', CashOutVerifyView.as_view(), name='cash-out-verify'),
]