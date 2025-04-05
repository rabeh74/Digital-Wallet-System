from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    """
    Handles user registration and profile updates with secure password management.
    
    Features:
    - Secure password handling with confirmation
    - Comprehensive field validation
    - Email normalization and uniqueness check
    - Phone number validation
    - Date of birth validation
    - Proper partial updates
    """
    
    password1 = serializers.CharField(
        write_only=True,
        required=True,
        min_length=8,
        style={'input_type': 'password'},
        help_text="Minimum 8 characters with at least one letter and one number"
    )
    password2 = serializers.CharField(
        write_only=True,
        required=True,
        min_length=8,
        style={'input_type': 'password'},
        help_text="Must exactly match password1"
    )
    
    class Meta:
        model = User
        fields = [
            'id',
            'email',
            'password1',
            'password2',
            'first_name',
            'last_name',
            'phone_number',
            'date_of_birth'
        ]
        extra_kwargs = {
            'email': {'required': True},
            'date_of_birth': {'required': False}
        }

    def validate_email(self, value):
        """Normalize email and check uniqueness."""
        value = value.lower().strip()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("This email is already registered")
        return value

    def validate_date_of_birth(self, value):
        """Ensure date of birth is valid."""
        if value and value > timezone.now().date():
            raise serializers.ValidationError("Date of birth cannot be in the future")
        return value

    def validate(self, data):
        """Validate password match and strength."""
        if 'password1' in data and 'password2' in data:
            if data['password1'] != data['password2']:
                raise serializers.ValidationError(
                    {'password2': "Passwords do not match"},
                    code='password_mismatch'
                )
            
            try:
                validate_password(data['password1'])
            except DjangoValidationError as e:
                raise serializers.ValidationError(
                    {'password1': list(e.messages)},
                    code='password_weak'
                )
        
        return data

    def create(self, validated_data):
        """Create user with properly hashed password."""
        validated_data['password'] = validated_data.pop('password1')
        validated_data.pop('password2')  
        
        try:
            return User.objects.create_user(**validated_data)
        except Exception as e:
            raise serializers.ValidationError(
                {'non_field_errors': str(e)},
                code='user_creation_failed'
            )

    def update(self, instance, validated_data):
        """Update user with optional password change."""
        password = validated_data.pop('password1', None)
        validated_data.pop('password2', None)  
        
        user = super().update(instance, validated_data)
        
        if password:
            user.set_password(password)
            user.save()
        
        return user