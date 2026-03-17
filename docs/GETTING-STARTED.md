# Getting Started with Campus

This guide helps you navigate the documentation based on your role and experience level.

## By Role

### 👨‍💻 New Developers
Start here if you're new to the codebase:
1. [CONTRIBUTING.md](CONTRIBUTING.md) - Development workflow and branch strategy
2. [development-guidelines.md](development-guidelines.md) - Coding patterns and best practices
3. [STYLE-GUIDE.md](STYLE-GUIDE.md) - Code standards and import patterns
4. [TESTING-GUIDE.md](TESTING-GUIDE.md) - How to run and write tests

### 🏗️ Experienced Developers
For those familiar with Python/Flask projects:
1. [architecture.md](architecture.md) - System design and service boundaries
2. [development-guidelines.md](development-guidelines.md) - Architecture patterns and abstractions
3. [PACKAGING.md](PACKAGING.md) - Monorepo structure and distribution

### 🚀 DevOps/Infrastructure
For deployment and operations:
1. [DEPLOY.md](../DEPLOY.md) - Deployment options
2. [PACKAGING.md](PACKAGING.md) - Build and distribution
3. [TESTING-GUIDE.md](TESTING-GUIDE.md) - Testing infrastructure

### 📚 End Users
For those deploying or using Campus:
1. [README.md](../README.md) - Project overview
2. [DEPLOY.md](../DEPLOY.md) - Deployment guide
3. [architecture.md](architecture.md) - System design

## Installation

### Prerequisites
- **pyenv** for Python version management
- **Python 3.11** (managed via pyenv)
- **pipx** for installing Poetry
- **Poetry** for dependency management (installed via pipx)
- PostgreSQL (for auth service database)
- MongoDB (optional, for alternative storage backend)

### Environment Setup

```bash
# 1. Install pyenv (Arch: pacman -S python-pyenv)
# 2. Install Python 3.11
pyenv install 3.11.11
pyenv local 3.11.11

# 3. Install Poetry via pipx (user-level, isolated)
pipx install --python python3.11 poetry

# 4. Configure PATH in ~/.bashrc:
export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/shims:$PATH"  # pyenv shims first
export PATH="$HOME/.local/bin:$PATH"    # pipx binaries
eval "$(pyenv init - bash)"
```

### Quick Setup

```bash
# Clone and enter directory
git clone https://github.com/nyjc-computing/campus.git
cd campus

# Install dependencies
poetry install

# Run the application
.venv/bin/python main.py
# OR
poetry run python main.py
```

### Environment Configuration

```bash
ENV="development"                     # deployment environment
CLIENT_ID="your-client-id"           # OAuth credentials
CLIENT_SECRET="your-client-secret"
POSTGRESDB_URI="postgresql://..."    # auth service database
```

Other configuration is managed via `campus.auth.vaults`.

## Documentation Index

| Document | Purpose |
|----------|---------|
| [AGENTS.md](../AGENTS.md) | Quick reference for humans and AI assistants |
| [architecture.md](architecture.md) | System design and component overview |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Development workflow and branch strategy |
| [development-guidelines.md](development-guidelines.md) | Coding patterns and best practices |
| [STYLE-GUIDE.md](STYLE-GUIDE.md) | Code standards and documentation |
| [TESTING-GUIDE.md](TESTING-GUIDE.md) | Testing approaches and strategies |
| [PACKAGING.md](PACKAGING.md) | Monorepo structure and distribution |

## Getting Help

- **[Issues](https://github.com/nyjc-computing/campus/issues)** - Bug reports and feature requests
- **[Discussions](https://github.com/nyjc-computing/campus/discussions)** - Questions and discussions
- **[security@nyjc.edu.sg](mailto:security@nyjc.edu.sg)** - Security vulnerabilities
