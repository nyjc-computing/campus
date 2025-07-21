# Campus Development Guide

Welcome to Campus development! This guide will help you understand our development workflow and get you contributing quickly.

## 🌳 Branch Structure

Campus uses a simple three-branch model designed for educational development:

```
weekly → staging → main
```

### Branch Purposes

- **`main`** - Stable, production-ready packages for external projects
- **`staging`** - Extended testing, migration validation, pre-production quality
- **`weekly`** - Active development, all new work, expected breakage welcome!

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

```bash
# Create your feature branch from weekly
git checkout weekly
git pull origin weekly
git checkout -b feature/your-feature-name

# Make your changes
# ... edit files ...

# Test your changes
poetry run python -m pytest
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

**Examples:**
```bash
# New authentication feature
git checkout weekly
git checkout -b feature/oauth-integration
# PR: feature/oauth-integration → weekly

# Fix package build issue  
git checkout weekly
git checkout -b fix/poetry-dependencies
# PR: fix/poetry-dependencies → weekly
```

## 🎯 Branch Promotion Flow (Maintainer Workflow)

**All promotions happen through Pull Requests to maintain transparency and teach best practices.**

### Weekly → Staging
After weekly sprint review, stable features get promoted:

```bash
# Create PR from weekly to staging
git checkout weekly
git pull origin weekly
# Create Pull Request: weekly → staging
# Title: "promote: weekly sprint [YYYY-MM-DD] to staging"
# Review and merge via GitHub UI
```

### Staging → Main
After extended validation (typically end of semester):

```bash
# Create PR from staging to main  
git checkout staging
git pull origin staging
# Create Pull Request: staging → main
# Title: "release: promote staging to production main"
# Review and merge via GitHub UI
# Tag the release: git tag v1.x.x && git push origin v1.x.x
```

### Direct Pushes (Limited Cases)
**Only for emergencies:**
- Security fixes requiring immediate deployment
- All other changes go through PRs

**Teaching Goal**: Contributors learn that production systems require review processes!

## 📦 Package Architecture

Campus is organized as modular packages:

```
campus/
├── common/         # Shared utilities (no dependencies)
├── vault/          # Secrets management (depends on common)
├── client/         # External API integrations (depends on common)
├── models/         # Data models (depends on common)
├── storage/        # Storage interfaces (depends on common + vault)
├── apps/           # Web applications (depends on all others)
└── workspace/      # Full deployment package (depends on all others)
```

### Key Principles

1. **Clear dependencies** - Follow the dependency flow diagram
2. **Independent builds** - Each package builds on its own
3. **Lazy loading** - External resources loaded only when needed
4. **Environment isolation** - Packages work without production secrets

## 🧪 Testing Your Changes

### Individual Package Testing

```bash
# Test a specific package builds
cd campus/vault && poetry build
cd campus/common && poetry build

# Run package tests
cd campus/vault && poetry run python -m pytest
```

### Full System Testing

```bash
# Run all tests
poetry run python -m pytest

# Test workspace integration
python -c "import campus.workspace; print('✅ Workspace works')"
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
