# Campus

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Flask 3.0+](https://img.shields.io/badge/flask-3.0+-green.svg)](https://flask.palletsprojects.com/)
[![Poetry](https://img.shields.io/badge/dependency%20management-poetry-blue.svg)](https://python-poetry.org/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A modular Python application framework for educational institution management, built with Flask and designed around clean architecture principles.

## 🏛️ Overview

Campus is a comprehensive educational management platform that provides:

- **User Management**: Student, teacher, and administrator accounts with role-based permissions
- **Circle Management**: Groups, classes, and organizational units with hierarchical permissions
- **Secure Authentication**: OAuth integration (Google) and email-based verification
- **Secrets Management**: Secure credential storage with fine-grained access control
- **Flexible Storage**: Multi-backend data persistence (PostgreSQL, MongoDB)
- **RESTful APIs**: Clean HTTP interfaces for all services
- **Modular Architecture**: Independent services that can be deployed separately or together

## 🚀 Quick Start

### Prerequisites

- Python 3.11 or higher
- Poetry for dependency management
- PostgreSQL (for vault and storage services)
- MongoDB (optional, for alternative storage backend)

### Installation

```bash
# Clone the repository
git clone https://github.com/nyjc-computing/campus.git
cd campus

# Install dependencies
poetry install

# Set up environment variables
cp .env.example .env
# Edit .env with your configuration

# Initialize the database
poetry run python -c "from campus.vault.db import init_db; init_db()"

# Run the application
poetry run python main.py
```

### Docker Setup (Alternative)

```bash
# Build and run with Docker Compose
docker-compose up -d

# The application will be available at http://localhost:5000
```

## 📁 Project Structure

```
campus/
├── 📄 README.md                    # This file - project overview
├── 📄 main.py                      # Application entry point
├── 📄 pyproject.toml              # Root project configuration
├── 📄 poetry.lock                 # Dependency lock file
├── 📄 docker-compose.yml          # Docker setup
├── 📄 .env.example                # Environment template
├── 📁 campus/                     # Main package namespace
│   ├── 📄 README.md               # Architecture overview
│   ├── 🌐 apps/                  # Web applications and API services
│   ├── 🔌 client/                # Client interfaces (HTTP-like APIs)
│   ├── 🛠️ common/                # Shared utilities and schemas
│   ├── 🏛️ models/                # Business logic and data models
│   ├── 📧 services/              # Supporting services (email, etc.)
│   ├── 💾 storage/               # Data persistence layer
│   ├── 🔐 vault/                 # Secrets management service
│   └── 📦 workspace/             # Deployment meta-package
├── 📁 docs/                      # Additional documentation
├── 📁 tests/                     # Test suite
├── 📁 migrations/                # Database migrations
└── 📁 deploy/                    # Deployment configurations
```

## 🏗️ Architecture

Campus follows a **modular monolith** architecture with clear service boundaries:

### Core Principles

- **🔄 Separation of Concerns**: Each service has a single, well-defined responsibility
- **🔌 Loose Coupling**: Services communicate through clean interfaces
- **🔐 Security First**: Authentication and authorization built into every layer
- **📈 Scalable**: Can be deployed as monolith or microservices
- **🧪 Testable**: Comprehensive test coverage with mocking support

### Service Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   🌐 Apps       │    │   🔌 Client     │    │   🛠️ Common     │
│   Web APIs      │    │   Interfaces    │    │   Utilities     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
         ┌───────────────────────┼───────────────────────┐
         │                       │                       │
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   🏛️ Models     │    │   🔐 Vault      │    │   📧 Services   │
│   Business      │    │   Secrets       │    │   Email, etc.   │
│   Logic         │    │   Management    │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                    ┌─────────────────┐
                    │   💾 Storage    │
                    │   Data Layer    │
                    └─────────────────┘
```

## 🔧 Configuration

Campus uses environment variables for configuration:

```bash
# Application - No SECRET_KEY needed (stored in vault)
FLASK_ENV="development"

# Vault Service
VAULTDB_URI="postgresql://user:pass@localhost/vault"
CLIENT_ID="your-vault-client-id"
CLIENT_SECRET="your-vault-client-secret"

# Storage Service
STORAGE_URI="postgresql://user:pass@localhost/campus"
# or: STORAGE_URI="mongodb://localhost:27017/campus"

# OAuth (optional)
GOOGLE_CLIENT_ID="your-google-client-id"
GOOGLE_CLIENT_SECRET="your-google-client-secret"

# Email Service (optional)
SMTP_SERVER="smtp.gmail.com"
SMTP_PORT="587"
SMTP_USER="your-email@gmail.com"
SMTP_PASS="your-app-password"
```

## 📚 Documentation

- **[📄 Campus Architecture](campus/README.md)** - Detailed architecture overview and design principles
- **[🔐 Vault Service](campus/vault/README.md)** - Secrets management and authentication
- **[🔌 Client Interfaces](campus/client/README.md)** - HTTP-like APIs and usage patterns
- **[📦 Workspace Package](campus/workspace/README.md)** - Deployment and platform compatibility
- **[🏛️ Models Documentation](campus/models/README.md)** - Business logic and data models
- **[💾 Storage Documentation](campus/storage/README.md)** - Data persistence and backends

## 🚀 Deployment

Campus supports multiple deployment strategies:

### 🔬 Development

```bash
# Individual service development
cd campus/vault && poetry install && poetry run python -m pytest

# Full system development  
poetry install && poetry run python main.py
```

### 🚀 Production (Integrated)

```bash
# Single application deployment
poetry install --no-dev
poetry run gunicorn main:app
```

### ☁️ Cloud Platforms

- **Replit**: Uses `campus.workspace` for compatibility
- **Heroku**: Standard Python buildpack with `Procfile`
- **Railway/Render**: Modern deployment platforms
- **AWS/GCP/Azure**: Container or serverless deployment

### 🐳 Docker

```bash
# Build and run
docker build -t campus .
docker run -p 5000:5000 campus

# With docker-compose (includes PostgreSQL)
docker-compose up -d
```

## 🧪 Testing

Campus includes comprehensive test coverage:

```bash
# Run all tests
poetry run python -m pytest

# Run specific service tests
poetry run python -m pytest tests/test_vault.py
poetry run python -m pytest tests/test_models.py

# Run with coverage
poetry run python -m pytest --cov=campus --cov-report=html
```

### Test Organization

- **Unit Tests**: Individual service functionality
- **Integration Tests**: Cross-service communication
- **API Tests**: HTTP endpoint validation
- **Client Tests**: Interface behavior verification

## 🔌 API Usage

Campus provides clean, HTTP-like interfaces:

### Vault (Secrets Management)

```python
import campus.client.vault as vault

# Store secrets
vault["database"].set("postgresql://...")
vault["api-key"].set("secret-key-123")

# Retrieve secrets
db_url = vault["database"].get()
api_key = vault["api-key"].get()

# List available secrets
secrets = vault.list_vaults()
```

### User Management

```python
import campus.client.users as users

# Create user
user = users.create(
    username="student123",
    email="student@school.edu",
    role="student"
)

# Retrieve user
user = users["student123"]
profile = user.get()

# Update user
user.update({"email": "new-email@school.edu"})
```

### Circle (Group) Management

```python
import campus.client.circles as circles

# Create circle
circle = circles.create(
    name="Math Class 2025",
    type="class",
    description="Advanced Mathematics"
)

# Add members
circle = circles["math-2025"]
circle.add_member("student123", role="student")
circle.add_member("teacher456", role="instructor")
```

## 🤝 Contributing

We welcome contributions! Please see our contributing guidelines:

### Development Setup

1. **Fork and Clone**:
   ```bash
   git clone https://github.com/your-username/campus.git
   cd campus
   ```

2. **Install Dependencies**:
   ```bash
   poetry install
   poetry run pre-commit install
   ```

3. **Create Feature Branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

4. **Make Changes and Test**:
   ```bash
   poetry run python -m pytest
   poetry run python -m pytest --cov=campus
   ```

5. **Submit Pull Request**:
   - Ensure tests pass
   - Add documentation for new features
   - Follow existing code style

### Guidelines

- **Architecture**: Follow established patterns in [campus/README.md](campus/README.md)
- **Testing**: Maintain high test coverage (>90%)
- **Documentation**: Update READMEs and docstrings
- **Security**: Never commit secrets or credentials
- **Modularity**: Keep services independent and loosely coupled

## 🔒 Security

- **Authentication**: Multi-factor with OAuth and email verification
- **Authorization**: Role-based with fine-grained permissions
- **Secrets**: Encrypted storage with access auditing
- **Transport**: HTTPS/TLS for all communication
- **Database**: Connection encryption and query parameterization

## 📋 Requirements

- **Python**: 3.11+ (for modern typing and performance)
- **Flask**: 3.0+ (latest security features)
- **PostgreSQL**: 12+ (for vault and primary storage)
- **MongoDB**: 4.4+ (optional alternative storage)
- **Poetry**: Any version (workspace package ensures compatibility)

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🏫 About

Campus is developed by the **NYJC Computing Department** as an open-source educational management platform. It's designed to be:

- **Educational**: Learn modern Python architecture patterns
- **Practical**: Solve real institutional management needs  
- **Flexible**: Adapt to different educational contexts
- **Scalable**: Grow from small schools to large universities

## 📞 Support

- **Documentation**: Check service-specific READMEs in [campus/](campus/)
- **Issues**: Report bugs via [GitHub Issues](https://github.com/nyjc-computing/campus/issues)
- **Discussions**: Ask questions in [GitHub Discussions](https://github.com/nyjc-computing/campus/discussions)
- **Security**: Report vulnerabilities to [security@nyjc.edu.sg](mailto:security@nyjc.edu.sg)

---

**Ready to get started?** Check out the [Campus Architecture Guide](campus/README.md) for detailed technical documentation.

## Installable Subpackages

The following subpackages can be installed independently. Each provides an `install.sh` script for reliable installation with all dependencies:

- `campus/client` — The client library for interacting with Campus APIs.
- `campus/vault` — The Vault service and related tools.
- `campus/apps` — The main application server and API endpoints.
- `campus/workspace` — The meta-package for a full Campus deployment (installs all components).

**To install any subpackage:**

```bash
cd campus/<subpackage>
bash install.sh
```

Replace `<subpackage>` with `client`, `vault`, `apps`, or `workspace` as needed.

> **Note:** Do not use `pip install` or `poetry install` directly for these subpackages unless you are developing locally. The install scripts ensure all dependencies are present and installed in the correct order.

For more details, see the README in each subpackage directory.
