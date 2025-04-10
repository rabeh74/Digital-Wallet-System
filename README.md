# Digital Wallet System

A modern digital wallet system built with Django and Django REST framework, providing secure and efficient financial transactions and management capabilities.

## Table of Contents

- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
- [Development](#development)
  - [Running Tests](#running-tests)
  - [Running Migrations](#running-migrations)
  - [Creating Superuser](#creating-superuser)
  - [Shell Access](#shell-access)
  - [Collect Static Files](#collect-static-files)
- [API Documentation](#api-documentation)
- [Environment Variables](#environment-variables)
- [Contributing](#contributing)
- [License](#license)

## Features

- User authentication and authorization with JWT
- Digital wallet management (create, view, update)
- Transaction processing (deposit, withdraw, transfer)
- Real-time transaction notifications using Celery
- Advanced filtering and ordering for wallets and transactions
- API documentation using drf-spectacular
- Background task processing with Celery
- Caching with Redis
- PostgreSQL database integration
- Comprehensive test suite

## Tech Stack

- **Backend**: Django 4.2.7
- **API Framework**: Django REST Framework 3.14.0
- **Authentication**: JWT Authentication
- **Database**: PostgreSQL 15
- **Caching**: Redis 4.5.5
- **Task Queue**: Celery 5.3.1
- **Containerization**: Docker Compose 3.8


## Project Structure

```
Digital-Wallet-System/
├── docker-compose.yml          # Docker configuration
├── Dockerfile                 # Docker build configuration
├── requirements.txt           # Python dependencies
├── .env                       # Environment variables
├── src/
│   ├── digital_wallet/        # Main Django project configuration
│   │   ├── settings.py
│   │   ├── urls.py
│   │   └── wsgi.py
│   ├── user/                  # User management app
│   │   ├── models.py
│   │   ├── views.py
│   │   └── serializers.py
│   ├── wallet/               # Wallet management app
│   │   ├── models.py
│   │   ├── views.py
│   │   ├── serializers.py
│   │   ├── tests/
│   │   │   ├── test_filters.py
│   │   │   ├── test_models.py
│   │   │   └── test_views.py
│   │   └── tasks.py
│   └── manage.py
└── static/                    # Static files
```

## Getting Started

### Prerequisites

- Docker and Docker Compose
- Git
- Basic understanding of Docker and Django

### Installation

1. **Clone the Repository**
   ```bash
   git clone https://github.com/yourusername/digital-wallet-system.git
   cd digital-wallet-system
   ```

2. **Build and Run**
   ```bash
   docker-compose up --build
   ```

3. **Access the Application**
   - API: `http://localhost:8000`
   - PostgreSQL: `localhost:5432`
   - Redis: `localhost:6379`
   - Swagger UI: `http://localhost:8000/api/schema/swagger-ui/`

## Development

### Running Tests

```bash
docker-compose run app python manage.py test
```

### Running Migrations

```bash
docker-compose run app python manage.py makemigrations
docker-compose run app python manage.py migrate
```

### Creating Superuser

```bash
docker-compose run app python manage.py createsuperuser
```

### Shell Access

```bash
docker-compose run app python manage.py shell
```

### Collect Static Files

```bash
docker-compose run app python manage.py collectstatic
```

## API Documentation

The API is documented using drf-spectacular. You can access the interactive Swagger UI at:

`http://localhost:8000/api/schema/swagger-ui/`

The API includes endpoints for:
- User management
- Wallet operations
- Transaction processing
- Transaction history
- Wallet balance retrieval

## Environment Variables

The project uses environment variables for configuration. Create a `.env` file with the following variables:

```
# Database Configuration
DB_NAME=wallet_db
DB_USER=wallet_user
DB_PASSWORD=wallet_password
DB_HOST=db
DB_PORT=5432

# Redis Configuration
REDIS_HOST=redis
REDIS_PORT=6379

# Celery Configuration
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0

# JWT Configuration
SECRET_KEY=your-secret-key
JWT_SECRET_KEY=your-jwt-secret-key

# Django Configuration
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Email Configuration (if needed)
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-email-password
```

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request
