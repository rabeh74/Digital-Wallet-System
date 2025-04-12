"""
Django settings for digital_wallet project.

Generated by 'django-admin startproject' using Django 5.1.5.

For more information on this file, see
https://docs.djangoproject.com/en/5.1/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/5.1/ref/settings/
"""

import environ
from pathlib import Path
from datetime import timedelta
import os

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.1/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('SECRET_KEY')

DEBUG = os.getenv('DEBUG', default=True)

ALLOWED_HOSTS = ['localhost', '127.0.0.1']

# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    #3rd party
    'rest_framework',
    'rest_framework_simplejwt',
    'drf_spectacular',
    'django_celery_beat',
    'django_celery_results',
    'django_filters',

    #apps
    'user',
    'wallet',
]

# Authentication
AUTH_USER_MODEL = 'user.CustomUser'

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'digital_wallet.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / "templates"],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'digital_wallet.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME'),
        'USER': os.getenv('DB_USER'),
        'PASSWORD': os.getenv('DB_PASSWORD'),
        'HOST': os.getenv('DB_HOST', default='db'),
        'PORT': os.getenv('DB_PORT', default='5432'),
    }
}


# Password validation
# https://docs.djangoproject.com/en/5.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.1/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True



# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.1/howto/static-files/

STATIC_URL='/static/static/'
MEDIA_URL='/static/media/'

STATIC_ROOT='/vol/web/static'
MEDIA_ROOT='/vol/web/media'


# Default primary key field type
# https://docs.djangoproject.com/en/5.1/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# JWT settings
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    
    'DEFAULT_FILTER_BACKENDS': ['django_filters.rest_framework.DjangoFilterBackend'],

    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',  
        'rest_framework.throttling.UserRateThrottle',  
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/day',  
        'user': '1000/day',
        'registration': '100/day',
        'wallet': '100/day',
    },
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=30),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

REST_FRAMEWORK['DEFAULT_SCHEMA_CLASS'] = 'drf_spectacular.openapi.AutoSchema'

SPECTACULAR_SETTINGS = {
'COMPONENT_SPLIT_REQUEST':True,
}

# Email Configuration
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'  # For testing
# For production, use SMTP:
# EMAIL_BACKEND = os.environ.get('EMAIL_BACKEND')
# EMAIL_HOST = os.environ.get('EMAIL_HOST')
# EMAIL_PORT = os.environ.get('EMAIL_PORT')
# EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS')
# EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER')
# EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL')

# Celery Configuration
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://:redis@redis:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://:redis@redis:6379/0')
CELERY_ACCEPT_CONTENT = ['json']  
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'
CELERY_BEAT_SCHEDULE = {
    'expire_old_transactions': {
        'task': 'wallet.tasks.expire_old_transactions',
        'schedule': 6 * 60 * 60 ,  # Run every 6 hours
    },
}

# PaySend Webhook Configuration
PAYSEND_WEBHOOK_SECRET = os.getenv('PAYSEND_WEBHOOK_SECRET')

# Cache Configuration
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': 'redis://:redis@redis:6379/1',  
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'PASSWORD': 'redis', 
        }
    }
}

CACHE_TIMEOUT = 60 * 15 



# IP whitelist
IP_WHITELIST = ['127.0.0.1', '0.0.0.0' , '172.17.0.1', '172.17.0.2']

# settings.py
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{asctime} {levelname} {module}.{funcName} {message} | user_id={user_id} wallet_id={wallet_id} transaction_ref={transaction_ref} amount={amount}',
            'style': '{',
        },
        'simple': {
            'format': '{asctime} {levelname} {message}',
            'style': '{',
        },
    },
    'filters': {
        'add_context': {
            '()': 'wallet.utils.ContextFilter',  # Custom filter defined later
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
            'level': 'DEBUG' if DEBUG else 'INFO',
        },
        'file_wallet': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(BASE_DIR, 'logs/wallet.log'),
            'maxBytes': 1024 * 1024 * 5,  # 5 MB
            'backupCount': 10,
            'formatter': 'verbose',
            'level': 'DEBUG',
            'filters': ['add_context'],
        },
        'file_celery': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(BASE_DIR, 'logs/celery.log'),
            'maxBytes': 1024 * 1024 * 5,
            'backupCount': 10,
            'formatter': 'verbose',
            'level': 'DEBUG',
            'filters': ['add_context'],
        },
    },
    'loggers': {
        'wallet.service': {
            'handlers': ['console', 'file_wallet'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        'wallet.views': {
            'handlers': ['console', 'file_wallet'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        'wallet.tasks': {
            'handlers': ['console', 'file_celery'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        'wallet.utils': {
            'handlers': ['console', 'file_wallet'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
    },
}

os.makedirs(os.path.join(BASE_DIR, 'logs'), exist_ok=True)