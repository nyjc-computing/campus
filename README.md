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
- **Secure Authentication**: OAuth integration (Google Workspace) and email-based verification
- **Secrets Management**: Secure credential storage with fine-grained access control
- **Flexible Storage**: Multi-backend data persistence (PostgreSQL, MongoDB)
- **RESTful APIs**: Clean HTTP interfaces for all services
- **Modular Architecture**: Independent services that can be deployed separately or together

## 🚀 Quick Start

### Prerequisites

- Python 3.11 or higher
- Poetry for dependency management
- PostgreSQL and MongoDB
  (for vault and storage services; extensible to support other storage backends)

### Installation

```bash
# Clone the repository
git clone https://github.com/nyjc-computing/campus.git
cd campus

# Install dependencies
poetry install

# Run the application
poetry run python main.py
```

> **Note**: Configuration is managed through environment variables and the vault service. See [Configuration](#-configuration) section below for details.

## 🏗️ Architecture

Campus follows a **modular monolith** architecture with clear service boundaries. Services can be deployed together or separately, each with well-defined responsibilities and clean interfaces.

**Key Components:**
- **Apps**: Web APIs and authentication
- **Vault**: Secure secrets management  
- **Storage**: Multi-backend data persistence
- **Client**: HTTP interfaces for external integration
- **Models**: Business logic and data models

For detailed architecture documentation, see [docs/architecture.md](docs/architecture.md).

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

- **[� Getting Started](docs/GETTING-STARTED.md)** - New user guide and navigation
- **[🏗️ Architecture](docs/architecture.md)** - Detailed architecture overview and design principles  
- **[🤝 Contributing](docs/CONTRIBUTING.md)** - Development workflow and guidelines
- **[🧪 Testing](docs/testing-strategies.md)** - Testing approaches and strategies
- **[📦 Packaging](docs/PACKAGING.md)** - Monorepo structure and distribution

**Service Documentation:**
- **[� Vault Service](campus/vault/README.md)** - Secrets management and authentication
- **[🔌 Client Interfaces](campus/client/README.md)** - HTTP APIs and usage patterns  
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

**Ready to get started?** Check out the [Getting Started Guide](docs/GETTING-STARTED.md) for step-by-step instructions.
