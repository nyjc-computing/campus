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

# Run the deployment
poetry run python main.py campus.auth  # or
poetry run python main.py campus.api
```

> **Note**: Configuration is managed through environment variables and the vault service. See [Configuration](#-configuration) section below for details.

## 🏗️ Architecture

Campus follows a **modular monolith** architecture with clear service boundaries.

**Key Components:**
- **Auth**: Authentication and OAuth (business logic in `.resources`)
- **API**: RESTful resources for circles, email OTP (business logic in `.resources`)
- **Model**: Entity representation (dataclasses only, no business logic)
- **Storage**: Backend-agnostic data persistence
- **Services**: Email, integrations

Access via `campus_python` client library. See [docs/architecture.md](docs/architecture.md).

## 🔧 Configuration

Campus uses environment variables for configuration:

```bash
ENV="development"                     # or "staging", "production"
DEPLOY="campus.auth"                  # campus.auth, campus.api, etc.
CLIENT_ID="your-client-id"           # Required for campus_python
CLIENT_SECRET="your-client-secret"
POSTGRESDB_URI="postgresql://..."    # Auth service database
```

Secrets managed via `campus.auth.vaults`, accessed through `campus_python` client.

## 📚 Documentation

- **[📖 Getting Started](docs/GETTING-STARTED.md)** - New user guide and navigation
- **[🏗️ Architecture](docs/architecture.md)** - Detailed architecture overview and design principles  
- **[🤝 Contributing](docs/CONTRIBUTING.md)** - Development workflow and guidelines
- **[🧪 Testing](docs/testing-strategies.md)** - Testing approaches and strategies
- **[📦 Packaging](docs/PACKAGING.md)** - Monorepo structure and distribution

**Service Documentation:**
- **[💾 Storage](campus/storage/README.md)** - Data persistence
- **[🛠️ Common](campus/common/README.md)** - Shared utilities

**Client**: See [campus-api-python](https://github.com/nyjc-computing/campus-api-python) for `campus_python` client docs.

## 🚀 Deployment

See [DEPLOY.md](DEPLOY.md).

### 🔬 Development

See [docs/development-guidelines.md](docs/development-guidelines.md).

## 🤝 Contributing

We welcome contributions! Please see our [contributing guidelines](docs/CONTRIBUTING.md).

### Guidelines

- Follow patterns in [campus/README.md](campus/README.md)
- Test coverage >90%
- Update docs and docstrings
- Never commit secrets
- Keep services independent

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
