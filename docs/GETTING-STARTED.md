
# Getting Started with Campus

Welcome to Campus! This guide helps you navigate the documentation based on your role and experience level.

## 👋 New to Campus?

**Start here:**
1. Read the [main README](../README.md) for project overview
2. Check out [Architecture](architecture.md) to understand the system design
3. Follow [Installation](#installation) steps below

## 🎯 Quick Navigation by Role

### 📚 End Users
- **[Deployment Guide](../DEPLOY.md)** — Deploy vault or full apps
- **API Documentation** — *Coming soon*
- **User Manual** — *Coming soon*

### 👨‍💻 New Developers  
- **[Contributing Guide](CONTRIBUTING.md)** — Development workflow and branch strategy
- **[Development Guidelines](development-guidelines.md)** — Coding patterns and best practices
- **[Style Guide](STYLE-GUIDE.md)** — Code and documentation standards
- **[Testing Strategies](testing-strategies.md)** — How to test your changes

### 🏗️ Experienced Developers
- **[Architecture](architecture.md)** — System design and service boundaries
- **[Packaging Guide](PACKAGING.md)** — Monorepo structure and distribution
- **[Development Guidelines](development-guidelines.md)** — Advanced patterns and abstractions

### 🚀 DevOps/Infrastructure
- **[Deployment Guide](../DEPLOY.md)** — Deployment options
- **[Packaging Guide](PACKAGING.md)** — Build and distribution
- **[Testing Strategies](testing-strategies.md)** — Testing infrastructure

## 🛠️ Installation

### Prerequisites
- Python 3.11 or higher
- Poetry for dependency management  
- PostgreSQL (for vault service)
- MongoDB (optional, for alternative storage backend)

### Quick Setup
```bash
# Clone and enter directory
git clone https://github.com/nyjc-computing/campus.git
cd campus

# Install dependencies
poetry install

# Run the application
poetry run python main.py
```

### Environment Configuration
```bash
ENV="development"                     # deployment environment
CLIENT_ID="your-client-id"           # OAuth credentials
CLIENT_SECRET="your-client-secret"   
POSTGRESDB_URI="postgresql://..."    # auth service database
```

Other configuration managed via `campus.auth.vaults`.

## 📖 Documentation Index

### Core Documentation
- **[Architecture](architecture.md)** — System design and component overview
- **[Contributing](CONTRIBUTING.md)** — Development workflow and guidelines  
- **[Development Guidelines](development-guidelines.md)** — Coding patterns and best practices
- **[Style Guide](STYLE-GUIDE.md)** — Code and documentation standards
- **[Testing Strategies](testing-strategies.md)** — Testing approaches and tools
- **[Packaging](PACKAGING.md)** — Monorepo structure and distribution

### Service-Specific Documentation
- **[Storage Layer](../campus/storage/README.md)** — Data persistence
- **[Common Utilities](../campus/common/README.md)** — Shared utilities

## 🆘 Need Help?

- **📋 Issues**: Report bugs via [GitHub Issues](https://github.com/nyjc-computing/campus/issues)
- **💬 Discussions**: Ask questions in [GitHub Discussions](https://github.com/nyjc-computing/campus/discussions)  
- **🔒 Security**: Report vulnerabilities to [security@nyjc.edu.sg](mailto:security@nyjc.edu.sg)

## 🏃‍♂️ Next Steps

1. **New Contributors**: Start with [CONTRIBUTING.md](CONTRIBUTING.md)
2. **Developers**: Review [development-guidelines.md](development-guidelines.md)  
3. **Users**: Check out [DEPLOY.md](../DEPLOY.md) for deployment options
