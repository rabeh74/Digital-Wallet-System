# Digital Wallet System

The Digital Wallet System is designed to handle financial operations efficiently, offering features like real-time transaction processing, secure webhook integrations, advanced caching, and background task automation. It’s ideal for developers building fintech applications or anyone interested in a modern, extensible wallet management platform.

## Features

### Core Features
- User Authentication & Authorization: Secure JWT-based authentication for users.
- Wallet Management: Create, view, and update digital wallets with ease.
- Transaction Processing: Supports deposits, withdrawals, and transfers with real-time updates.
- Real-Time Notifications: Sends transaction updates via email or other channels using Celery tasks.
- Advanced Filtering & Ordering: Flexible querying for wallets and transactions (e.g., by amount, type, status).
- API Documentation: Interactive Swagger UI and ReDoc via drf-spectacular.
- Background Task Processing: Asynchronous task execution with Celery and Redis.
- Caching: Redis-backed caching for optimized performance.
- Database: PostgreSQL for reliable, transactional data storage.
- Comprehensive Testing: Extensive unit and integration tests Django’s test framework.

### Security Features
- JWT Authentication: Token-based access control for API endpoints.
- Webhook Security:
  - HMAC-SHA256 Signature Verification: Ensures webhook payloads are authentic.
  - IP Whitelisting: Restricts webhook access to trusted IP addresses.
  - Rate Limiting: Throttles API requests to prevent abuse (configurable per endpoint).
  - Idempotency: Prevents duplicate processing of webhook requests and user actions using Idempotency-Key.
- Transaction Validation: Robust error handling and validation for all financial operations.
- CSRF Protection: Exempted safely for webhooks with additional security layers.

## Performance Features
- Caching Strategy:
  - Transaction lists cached for 15 minutes with keys like `transaction_list_{user_id}_page_{page}_size_{size}`.
  - Automatic cache invalidation via signals on transaction creation.
  - 24-hour idempotency caching with keys like `idempotency_{key}`.
- Asynchronous Processing: Celery tasks for notifications, transaction expiry, and background jobs.
- Database Optimization: Efficient queries and indexing for transaction filtering and ordering.

## Extensibility
- Modular Design: Apps (user, wallet) and reusable utilities for easy expansion.
- Service Layer: Business logic abstracted with design patterns for flexibility.
- Webhook Support: Extensible framework for integrating with third-party services (e.g., Paysend).

## Tech Stack

- Backend: Django 4.2.7
- API Framework: Django REST Framework 3.14.0
- Authentication: JWT (JSON Web Tokens)
- Caching: Redis
- Message Queue: Celery with Redis as broker
- Database: PostgreSQL
- Testing: Django Test Client
- API Documentation: drf-spectacular
- Development Tools: Docker, Docker Compose

## Project Structure

```
digital-wallet-system/
├── src/
│   ├── digital_wallet/     # Main Django project settings
│   │   ├── settings.py     # Configuration
│   │   └── urls.py        # Root URL routing
│   ├── user/              # User management app
│   │   ├── models.py      # User models
│   │   ├── views.py       # User API views
│   │   ├── serializers.py # User serializers
│   │   └── tests/         # User tests
│   └── wallet/            # Wallet and transaction app
│       ├── models.py      # Wallet and Transaction models
│       ├── views.py       # API views (WalletViewSet, webhook views)
│       ├── serializers.py # API serializers
│       ├── service.py     # WalletService and strategies
│       ├── filters.py     # Custom filters for transactions
│       ├── utils.py       # Utilities (e.g., IdempotencyChecker)
│       ├── signals.py     # Signals (e.g., cache invalidation)
│       ├── tasks.py       # Celery tasks (e.g., notifications, expiry)
│       └── tests/         # Wallet tests
├── docker-compose.yml     # Docker Compose configuration
├── requirements.txt       # Python dependencies
└── .env.example           # Sample environment variables
```

## Architecture & Design Patterns

### Service Layer
- Repository Pattern: Abstracts data access with IWalletRepository and ITransactionRepository.
- Strategy Pattern: Implements transaction logic with DepositStrategy, WithdrawalStrategy, and TransferStrategy.
- Command Pattern: Manages transaction state changes with AcceptTransactionCommand and RejectTransactionCommand.
- Factory Pattern: Instantiates services via WalletServiceFactory.

### Caching Strategy
- Redis-Based Caching:
  - Transaction lists: 15-minute timeout, keys like transaction_list_{user_id}_page_{page}_size_{size}.
  - Idempotency: 24-hour timeout, keys like idempotency_{key}.
- Cache Invalidation: Signals invalidate cache on transaction creation using cache.delete_pattern.

### Throttling
- **Rate limiting**: 
  - Anonymous users: 100 requests/day
  - Authenticated users: 1000 requests/day
  - Registration: 100 requests/day
  - Wallet operations: 100 requests/day

### Webhook Processing
- **Idempotency**: Prevents duplicate processing of webhook requests
- **Signature verification**: Ensures webhook requests are from authorized sources
- **IP whitelisting**: Restricts webhook access to trusted IPs

### Background Processing
- **Celery Tasks**:
  - Real-time notifications (send_transaction_notification).
  - Transaction expiry (expire_old_transactions) scheduled via Celery Beat.
  - Redis Broker: Ensures reliable task queuing and execution.

## API Documentation

### Endpoints

#### Wallet Management
- `GET /api/v1/wallet/` - List wallets
- `POST /api/v1/wallet/` - Create wallet
- `GET /api/v1/wallet/{id}/` - Retrieve wallet

#### Transaction Management
- `GET /api/v1/wallet/transactions/` - List transactions
- `POST /api/v1/wallet/transactions/` - Process transaction
- `POST /api/v1/wallet/transactions/{id}/action/` - Accept/reject transaction

#### Webhooks
- `POST /api/v1/wallet/webhook/paysend/` - Process Paysend webhook
- `POST /api/v1/wallet/webhook/cashout/` - Process cashout verification

### Filtering & Ordering
- **Transaction Filtering**:
  - Amount range (`amount_min`, `amount_max`)
  - Transaction type
  - Funding source
  - Status
  - Reference text
  - Creation date range
  - Expiry time range
  - Involving user (sender or recipient)

- **Ordering**:
  - Amount
  - Creation date
  - Expiry time
  - Transaction type
  - Status
  - User username

## Development

### Prerequisites
- Python 3.8+
- PostgreSQL
- Redis
- Docker and Docker Compose (optional)

### Installation

#### Option 1: Local Development (Virtual Environment)
```bash
# Clone the repository
git clone https://github.com/rabeh74/Digital-Wallet-System.git
cd Digital-Wallet-System

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env with your configuration

# Apply migrations
python manage.py migrate

# Run the development server
python manage.py runserver
```

#### Option 2: Docker Development
```bash
# Clone the repository
git clone https://github.com/rabeh74/Digital-Wallet-System.git
cd Digital-Wallet-System

# Copy and configure environment variables
cp .env.example .env
# Edit .env as needed

# Build and start containers
docker-compose up --build

# Access services:
# - API: http://localhost:8000
# - PostgreSQL: localhost:5432
# - Redis: localhost:6379
# - Swagger UI: http://localhost:8000/api/schema/swagger-ui/
# - ReDoc: http://localhost:8000/api/schema/redoc/

# Run migrations
docker-compose run app python manage.py migrate

# Create superuser
docker-compose run app python manage.py createsuperuser

# Run tests
docker-compose run app python manage.py test
```

### Running Tests
```bash
# Run all tests
python manage.py test

# Run specific tests
python manage.py test wallet.tests.test_transactions
```

### Running Migrations
```bash
# Create and apply migrations
python manage.py makemigrations
python manage.py migrate
```

### Creating Superuser
```bash
python manage.py createsuperuser
```

### Shell Access
```bash
python manage.py shell
```

### Collect Static Files
```bash
python manage.py collectstatic
```

## Environment Variables

```bash
# Core Settings
DEBUG=True
SECRET_KEY=your-secret-key
ALLOWED_HOSTS=localhost,127.0.0.1

# Database
DATABASE_URL=postgres://user:password@localhost:5432/wallet_db

# Redis
REDIS_URL=redis://localhost:6379/0

# Celery
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# Email
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-specific-password
DEFAULT_FROM_EMAIL=your-email@gmail.com

# Paysend Webhook
PAYSEND_WEBHOOK_SECRET=your-paysend-webhook-secret

# IP Whitelisting
IP_WHITELIST=127.0.0.1,0.0.0.0,172.17.0.1,172.17.0.2

# Environment
ENV=True
```
