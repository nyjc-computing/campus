# Campus Development Guide

Welcome to Campus development! This guide will help you understand our development workflow and get you contributing quickly.

## 🌳 Branch Structure

Campus uses a simple three-branch model designed for educational development:

# Contributing to Campus

Welcome to Campus development! This guide covers our development workflow and contribution process.

## 🌳 Branch Structure

Campus uses a three-branch model for educational development:

```
weekly → staging → main
```

### Branch Purposes

- **`main`** - Stable, production-ready releases
  - Only accepts PRs from `staging`
  - Requires project owner approval
- **`staging`** - Extended testing and pre-production validation
  - Requires PR with review
- **`weekly`** - Active development, all new work
  - Requires PR (review recommended for major features)

## 🚀 Quick Start

### 1. Initial Setup

```bash
# Clone repository and switch to development branch
git clone https://github.com/nyjc-computing/campus.git
cd campus
git checkout weekly

# Install dependencies (monorepo with single pyproject.toml)
poetry install
```

### 2. Development Workflow

All changes use GitHub Pull Requests:

```bash
# Create feature branch from weekly
git checkout weekly
git pull origin weekly
git checkout -b feature/your-feature-name

# Make changes and test
poetry run python -m pytest tests/
poetry run python main.py  # Test application starts

# Commit with descriptive message
git add .
git commit -m "feat: describe your changes"
git push origin feature/your-feature-name

# Create PR to weekly branch via GitHub UI
```

### 3. Pull Request Guidelines

**Target Branch**: Always target `weekly` for development work

**PR Title Format**: Use conventional commits:
- `feat:` - New features
- `fix:` - Bug fixes  
- `docs:` - Documentation changes
- `test:` - Adding tests
- `refactor:` - Code restructuring

**Description**: Include what changed, why, and how to test

## 🧪 Testing Your Changes

See [Testing Strategies](testing-strategies.md) for comprehensive testing approaches.

**Quick Testing**:
```bash
# Run unit tests
poetry run pytest tests/unit/

# Test package imports
poetry run python -c "import campus.vault, campus.storage, campus.apps"

# Start application
poetry run python main.py
```

## 📦 Package Structure

Campus is a monorepo with these key packages:

```
campus/
├── common/     # Shared utilities (no dependencies)
├── vault/      # Secrets management (depends on common)
├── storage/    # Data persistence (depends on common + vault)
├── models/     # Business logic (depends on common)
├── apps/       # Web applications (depends on all others)
└── client/     # HTTP client library
```

### Dependency Rules
- `vault` imports only from `common` (must be independent)
- `storage` can use `vault` for database secrets
- `apps` can import from any package
- Follow the import guidelines in [Style Guide](STYLE-GUIDE.md)

## 🔀 Branch Promotion (Maintainers)

### Weekly → Staging
After sprint review, promote stable features:
```bash
# Create PR: weekly → staging
# Title: "promote: weekly sprint [date] to staging"
```

### Staging → Main  
After extended validation:
```bash
# Create PR: staging → main
# Title: "release: promote staging to production"
# Tag release after merge: git tag v1.x.x
```

### Automatic Downstream Flow
Changes in higher branches automatically sync downstream:
- `main` → `staging` → `weekly` (automated)

## 🎯 Best Practices

### Code Quality
- Follow [Style Guide](STYLE-GUIDE.md) for coding standards
- Write tests for new features
- Update documentation for changes
- Use `poetry run python` instead of bare `python`

### Common Pitfalls
- **Environment**: Always use `poetry run python` for consistent environment
- **Imports**: Import packages not individual functions (see [Style Guide](STYLE-GUIDE.md))
- **Dependencies**: Update `pyproject.toml` for new dependencies
- **Testing**: Test locally before pushing

### Commit Messages
Follow conventional commit format:
```bash
feat(vault): add encrypted secret storage
fix(storage): resolve PostgreSQL connection timeout
docs(api): update authentication examples
```

## 🆘 Getting Help

- **Code Reviews**: See [code review best practices](https://nyjc-computing.github.io/nanyang-system-developers/contributors/training/code-reviews.html)
- **Issues**: Report bugs via [GitHub Issues](https://github.com/nyjc-computing/campus/issues)
- **Discussions**: Ask questions in [GitHub Discussions](https://github.com/nyjc-computing/campus/discussions)

## 📚 Additional Resources

- **[Architecture](architecture.md)** - System design overview
- **[Development Guidelines](development-guidelines.md)** - Coding patterns and abstractions
- **[Testing Strategies](testing-strategies.md)** - Testing approaches
- **[Style Guide](STYLE-GUIDE.md)** - Code and documentation standards

### Branch Purposes

- **`main`** - Stable, production-ready packages for external projects
  - ✔️ only PR from `staging` is allowed
  - 🛡️ requires approval from project owner
- **`staging`** - Extended testing, migration validation, pre-production quality
  - ✔️ requires PR
  - 🔒 PR **must have** at least one review
- **`weekly`** - Active development, all new work, expected breakage welcome!
  - ✔️ requires PR
  - 👀 PR for critical/major features **should be** reviewed by a collaborator

Bugfixes, CI/CD work, general documentation updates may be PRed to `staging` directly if urgent and does not need to pass through weekly review

## 🚀 Getting Started

### 1. Initial Setup

```bash
# Clone the repository
git clone https://github.com/nyjc-computing/campus.git
cd campus

# Switch to active development branch
git checkout weekly

# Install dependencies
poetry install
```

### 2. Development Workflow

**We use GitHub Pull Requests for all changes to teach proper collaborative development practices.**

See our best practices on [code reviews](https://nyjc-computing.github.io/nanyang-system-developers/contributors/training/code-reviews.html)

```bash
# Create your feature branch from weekly
git checkout weekly
git pull origin weekly
git checkout -b feature/your-feature-name

# Make your changes
# ... edit files ...

# Test your changes
python run_tests.py
cd campus/vault && poetry build  # Test individual packages

# Commit and push
git add .
git commit -m "feat: describe your changes"
git push origin feature/your-feature-name
```

### 3. Create Pull Request (Required!)

**All changes must go through Pull Requests - no direct pushes to weekly/staging/main.**

1. **Go to GitHub** and create a Pull Request
2. **Target branch**: `weekly` (for all development work)
3. **Title**: Clear, descriptive title (e.g., "feat: add user authentication", "fix: resolve import circular dependency")
4. **Description**: 
   - What you changed and why
   - Testing you performed
   - Any breaking changes or special considerations

### 4. PR Review Process

- **Automated checks**: CI/CD will test your changes across all packages
- **Code review**: Maintainers or peers review your code
- **Feedback**: Address any requested changes
- **Approval**: Once approved, maintainers will merge

**Educational Goal**: This mirrors real-world software development practices!

### 5. Choosing the Right Target Branch

**For all development work:**
- **Target**: `weekly` 
- **Use for**: New features, bug fixes, experiments, infrastructure improvements

**Never target `main` or `staging` directly** - these are managed through the promotion flow.

## 🎯 Branch Promotion Flow (Maintainer Workflow)

**All promotions happen through Pull Requests to maintain transparency and teach best practices.**

### Upstream Flow (Requires PRs)
**All promotions to higher stability levels require Pull Requests and review.**

#### Weekly → Staging
After weekly sprint review, stable features get promoted:

```bash
# Create PR from weekly to staging
git checkout weekly
git pull origin weekly
# Create Pull Request: weekly → staging
# Title: "promote: weekly sprint [YYYY-MM-DD] to staging"
# Review and merge via GitHub UI
```

#### Staging → Main
After extended validation (typically end of term):

```bash
# Create PR from staging to main  
git checkout staging
git pull origin staging
# Create Pull Request: staging → main
# Title: "release: promote staging to production main"
# Review and merge via GitHub UI
# Tag the release: git tag v1.x.x && git push origin v1.x.x
```

### Downstream Flow (Automatic)
**Changes flow automatically from higher to lower stability branches since they were already reviewed.**

#### Main → Staging & Weekly
When changes are merged to `main`, they automatically flow downstream:
- **Main → Staging**: Automated merge (no PR needed)
- **Main → Weekly**: Automated merge (no PR needed)
- **Staging → Weekly**: Automated merge when staging is updated

**Rationale**: These changes were already reviewed and approved when going upstream, so they should be reflected in all downstream environments without manual overhead.

### Direct Pushes (Limited Cases)
**Only for emergencies:**
- Security fixes requiring immediate deployment
- All other changes go through the upstream PR flow

**Teaching Goal**: Contributors learn that production systems require review processes, but approved changes flow efficiently downstream!

## 📦 Package Architecture

Campus is organized as modular packages:

```
campus/
├── common/         # Shared utilities (no dependencies)
├── vault/          # Secrets management (depends on common)
├── client/         # External API integrations (depends on common)
├── models/         # Data models (depends on common)
├── storage/        # Storage interfaces (depends on common + vault)
└── apps/           # Web applications (depends on all others)
```

### Key Principles

1. **Clear dependencies** - Follow the dependency flow diagram
2. **Independent builds** - Each package builds on its own
3. **Lazy loading** - External resources loaded only when needed
4. **Environment isolation** - Packages work without production secrets

## 🧪 Testing Your Changes

Campus provides **three testing strategies** for different scenarios. See **[Testing Strategies](testing-strategies.md)** for comprehensive documentation.

**Quick Summary**:
- **Unit tests**: `poetry run python tests/run_tests.py unit` (Flask test clients)
- **Integration tests**: `poetry run python tests/run_tests.py integration` (local services)  
- **Manual testing**: Set `ENV=development` (Railway services)

### Individual Package Testing

```bash
# Test a specific package builds
cd campus/vault && poetry build
cd campus/common && poetry build

# Run package tests
python run_tests.py
```

### Full System Testing

```bash
# Run all tests
python run_tests.py

# (If you need to test integration across packages, ensure all relevant packages are installed and importable.)
# Example:
# python -c "import campus.client, campus.vault; print('✅ Core packages import successfully')"
```

### CI/CD Validation

Our GitHub Actions will automatically:
- Build all packages independently
- Run the full test suite
- Validate dependency ordering
- Check for import issues

## 🎓 Educational Goals

This workflow teaches:

- **Industry-standard branching** (weekly/staging/main mirrors dev/staging/production)
- **Release management** (controlled promotion between environments)
- **Quality gates** (testing at each stability level)
- **Modular architecture** (independent, composable packages)

## 📋 Contribution Guidelines

### Code Style

- Follow existing patterns in the codebase
- Use type hints where appropriate
- Add docstrings for public functions
- Keep functions focused and testable

### Commit Messages

Use conventional commit format:
```
feat: add new user authentication method
fix: resolve circular import in storage module  
docs: update API documentation
test: add coverage for vault access controls
```

### Testing Requirements

- Add tests for new functionality
- Ensure existing tests still pass
- Test package builds independently
- Update documentation as needed

## 🔧 Development Environment

### Required Tools

- **Python 3.11+** - Language runtime
- **Poetry** - Dependency management
- **Git** - Version control

### Recommended Setup

```bash
# Install Poetry if not already installed
curl -sSL https://install.python-poetry.org | python3 -

# Configure Poetry for this project
poetry config virtualenvs.in-project true
poetry install

# Install pre-commit hooks (optional)
poetry run pre-commit install
```

## 🚨 Common Issues

### Import Errors
- Check dependency ordering in the package architecture
- Ensure you're importing from the correct package
- Use lazy loading for external resources

### Build Failures
- Verify all dependencies are in pyproject.toml
- Check for circular dependencies
- Ensure environment variables are handled gracefully

### Test Failures
- Run tests locally before pushing
- Check that mock data is properly set up
- Verify database connections use lazy loading

## 📞 Getting Help

- **Documentation**: Check package-specific READMEs in each `campus/` subdirectory
- **Issues**: Report bugs via [GitHub Issues](https://github.com/nyjc-computing/campus/issues)
- **Discussions**: Ask questions in [GitHub Discussions](https://github.com/nyjc-computing/campus/discussions)
- **Code Review**: Tag maintainers in your pull requests

## 🏫 Academic Context

Campus is developed by the **NYJC Computing Department** as both:
- **Educational tool** - Learn modern Python architecture patterns
- **Practical platform** - Solve real institutional management needs

Your contributions help other developers learn while building something genuinely useful!

---

**Ready to contribute?** Create your feature branch from `weekly` and start building! 🚀
