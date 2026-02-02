# Contributing to Campus

Welcome to Campus development! This guide covers our development workflow and contribution process.

## 🌳 Branch Structure

Campus uses a three-branch model:

```
weekly → staging → main
```

- **`weekly`** - Active development (target for all new work)
- **`staging`** - Pre-production validation (requires review)
- **`main`** - Production releases (maintainer only)

## 🚀 Quick Start

### 1. Setup

```bash
git clone https://github.com/nyjc-computing/campus.git
cd campus
git checkout weekly
poetry install

# Set up pre-push hook to catch sanity check failures early
git config core.hooksPath .githooks
```

The pre-push hook will run sanity checks before allowing pushes to GitHub. This saves time by catching issues locally before CI/CD runs. To bypass the hook (not recommended): `git push --no-verify`

### 2. Create Feature

```bash
# Create branch from weekly
git checkout weekly
git pull origin weekly
git checkout -b feature/your-feature-name

# Make changes and test
poetry run python run_tests.py
poetry run python main.py

# Commit and push
git add .
git commit -m "feat: describe your changes"
git push origin feature/your-feature-name
```

### 3. Pull Request

1. Create PR targeting `weekly` branch
2. Use conventional commit format in title:
   - `feat:` - New features
   - `fix:` - Bug fixes
   - `docs:` - Documentation
   - `test:` - Tests
   - `refactor:` - Code restructuring

## 🧪 Testing

**⚠️ IMPORTANT: Always use `run_tests.py` as the entrypoint for running tests.**

```bash
# Run all tests (sanity, type, unit, integration)
poetry run python run_tests.py

# Run specific test categories
poetry run python run_tests.py unit        # Unit tests only
poetry run python run_tests.py integration # Integration tests only
poetry run python run_tests.py sanity      # Sanity checks only
poetry run python run_tests.py type        # Type checks only
```

**Do NOT run tests directly with `unittest` or `pytest`** - the test entrypoint handles proper environment setup, cleanup, and isolation between test classes. Running tests directly may produce false positives or miss failures.

See [Testing Strategies](testing-strategies.md) for comprehensive approaches.

## 📦 Package Structure

```
campus/
├── auth/       # Authentication and OAuth services
│   ├── oauth_proxy/
│   ├── resources/
│   └── routes/
├── api/        # RESTful API resources
│   ├── resources/
│   └── routes/
├── common/     # Shared utilities
├── model/      # Entity representation (dataclasses)
├── services/   # Business services (email, etc.)
├── storage/    # Data persistence layer
├── integrations/# External service integrations
└── yapper/     # Logging framework
```

### Key Rules

- `auth` and `api` contain business logic in `.resources` submodules
- `model` contains only entity definitions (no business logic)
- Use `poetry run python` for consistency
- Follow [Style Guide](STYLE-GUIDE.md) for imports and coding standards

## 🎯 Best Practices

### Code Quality
- Write tests for new features
- Update documentation for changes
- Use type hints and docstrings
- Follow existing patterns

### Commit Messages
```bash
feat(auth): add OAuth provider support
fix(storage): resolve PostgreSQL connection timeout
docs(api): update circle management examples
```

### Common Pitfalls
- Use `poetry run python` not bare `python`
- Import packages not individual functions
- Update `pyproject.toml` for new dependencies
- Test locally before pushing

## 🔀 Maintainer Workflow

### Weekly → Staging
```bash
# After sprint review
# Create PR: weekly → staging
# Title: "T3W10: weekly PR"
```

### Staging → Main
```bash
# After validation
# Create PR: staging → main
# Title: "v0.2 release: staging PR"
```

## 🆘 Getting Help

- **Issues**: [GitHub Issues](https://github.com/nyjc-computing/campus/issues)
- **Discussions**: [GitHub Discussions](https://github.com/nyjc-computing/campus/discussions)
- **Code Reviews**: [Best Practices](https://nyjc-computing.github.io/nanyang-system-developers/contributors/training/code-reviews.html)

## 📚 Documentation

- **[Architecture](architecture.md)** - System design
- **[Development Guidelines](development-guidelines.md)** - Coding patterns
- **[Testing Strategies](testing-strategies.md)** - Testing approaches
- **[Style Guide](STYLE-GUIDE.md)** - Code standards

## 🎓 Educational Goals

This workflow teaches:
- Industry-standard branching (weekly/staging/main)
- Release management and quality gates
- Modular architecture patterns
- Collaborative development practices

---

**Ready to contribute?** Create your feature branch from `weekly` and start building! 🚀
