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
# Environment Configuration
ENV="development"  # or "staging", "production"

# Client Authentication (Required for campus.client)
CLIENT_ID="your-client-id"
CLIENT_SECRET="your-client-secret"

# Vault Database (Only required when using campus.vault service)
VAULTDB_URI="postgresql://user:pass@localhost/vault"

All other configuration (storage, OAuth, email, etc.) is managed through campus.vault
and should not be set as environment variables. Use the vault service to manage these
secrets securely.
```

## 📚 Documentation

- **[📄 Campus Architecture](campus/README.md)** - Detailed architecture overview and design principles
- **[🔐 Vault Service](campus/vault/README.md)** - Secrets management and authentication
- **[🔌 Client Interfaces](campus/client/README.md)** - HTTP-like APIs and usage patterns
- **[📦 Workspace Package](campus/workspace/README.md)** - Deployment and platform compatibility
- **[🏛️ Models Documentation](campus/models/README.md)** - Business logic and data models
- **[💾 Storage Documentation](campus/storage/README.md)** - Data persistence and backends

## 🚀 Deployment

See [DEPLOY.md](DEPLOY.md).

### 🔬 Development

See [docs/development-guidelines.md](docs/development-guidelines.md).

## 🤝 Contributing

We welcome contributions! Please see our [contributing guidelines](docs/CONTRIBUTING.md).

### Guidelines

- **Architecture**: Follow established patterns in [campus/README.md](campus/README.md)
- **Testing**: Maintain high test coverage (>90%)
- **Documentation**: Update READMEs and docstrings
- **Security**: Never commit secrets or credentials
- **Modularity**: Keep services independent and loosely coupled

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
