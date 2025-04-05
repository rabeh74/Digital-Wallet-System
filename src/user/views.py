from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework.response import Response
from rest_framework import generics, permissions, status
from .serializers import UserSerializer
from .filters import UserFilter
from django.contrib.auth import get_user_model
from .permissions import IsOwner

User = get_user_model()

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Custom JWT token serializer that adds additional user claims to the token payload.
    
    Includes:
    - User email
    - First name (if available)
    - Last name (if available)
    """
    
    @classmethod
    def get_token(cls, user):
        """Add custom claims to the JWT token payload."""
        token = super().get_token(user)
        
        # Add custom claims
        token['email'] = user.email
        token['first_name'] = user.first_name or ''
        token['last_name'] = user.last_name or ''
        token['is_staff'] = user.is_staff
        
        return token

class CustomTokenObtainPairView(TokenObtainPairView):
    """
    Custom JWT token obtain view that uses our enhanced serializer.
    
    Returns:
    - Access token
    - Refresh token
    - User email in token payload
    """
    serializer_class = CustomTokenObtainPairSerializer

class UserCreateView(generics.CreateAPIView):
    """
    Public endpoint for user registration.
    
    Allows any user (authenticated or not) to register a new account.
    Performs password validation and email uniqueness checks.
    """
    permission_classes = (permissions.AllowAny,)
    serializer_class = UserSerializer
    throttle_scope = 'registration'

    def create(self, request, *args, **kwargs):
        """Handle user creation with proper response formatting."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        
        headers = self.get_success_headers(serializer.data)
        return Response(
            {
                'status': 'success',
                'data': serializer.data,
                'message': 'User created successfully'
            },
            status=status.HTTP_201_CREATED,
            headers=headers
        )

class UserRetrieveUpdateView(generics.RetrieveUpdateAPIView):
    """
    Endpoint for authenticated users to view and update their profile.
    
    Features:
    - Only allows users to access their own profile
    - Supports partial updates
    - Handles password changes securely
    """
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated , IsOwner]
    queryset = User.objects.all()


    def update(self, request, *args, **kwargs):
        """Handle profile updates with proper response formatting."""
        partial = kwargs.pop('partial', True)
        instance = self.get_object()
        
        serializer = self.get_serializer(
            instance, 
            data=request.data, 
            partial=partial
        )
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        
        if getattr(instance, '_prefetched_objects_cache', None):
            instance._prefetched_objects_cache = {}
            
        return Response(
            {
                'status': 'success',
                'data': serializer.data,
                'message': 'Profile updated successfully'
            }
        )

class UserListView(generics.ListAPIView):
    """
    Admin-only endpoint for listing all users.
    
    Features:
    - Requires admin privileges
    - Supports filtering by various fields
    - Pagination support
    """
    serializer_class = UserSerializer
    permission_classes = (permissions.IsAdminUser,)
    queryset = User.objects.all().order_by('-date_joined')
    filterset_class = UserFilter
    
    def list(self, request, *args, **kwargs):
        """Format list response with metadata."""
        queryset = self.filter_queryset(self.get_queryset())
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(
            {
                'status': 'success',
                'count': queryset.count(),
                'data': serializer.data
            }
        )
    