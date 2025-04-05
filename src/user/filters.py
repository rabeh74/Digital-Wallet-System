from django_filters import rest_framework as filters
from django.contrib.auth import get_user_model

User = get_user_model()

class UserFilter(filters.FilterSet):
    email = filters.CharFilter(lookup_expr='icontains')
    first_name = filters.CharFilter(lookup_expr='icontains')
    last_name = filters.CharFilter(lookup_expr='icontains')
    is_staff = filters.BooleanFilter()
    is_active = filters.BooleanFilter()

    class Meta:
        model = User
        fields = ['email', 'first_name', 'last_name', 'is_staff', 'is_active']