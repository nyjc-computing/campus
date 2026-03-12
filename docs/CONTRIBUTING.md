# Contributing to Campus

This guide covers our development workflow, branch strategy, and contribution process.

**New here?** See [GETTING-STARTED.md](GETTING-STARTED.md) for installation instructions.

## Branch Strategy

Campus uses a three-branch model:

```
weekly → staging → main
```

| Branch | Purpose | Who Commits |
|--------|---------|-------------|
| `weekly` | Active development | All contributors |
| `staging` | Pre-production validation | Maintainers (via PR) |
| `main` | Production releases | Maintainers (via PR) |

## Workflow

### 1. Create a Feature Branch

```bash
# Start from weekly
git checkout weekly
git pull origin weekly

# Create your feature branch
git checkout -b feature/your-feature-name
```

### 2. Make Changes

```bash
# Run tests before committing
poetry run python tests/run_tests.py

# Commit with conventional commit format
git add .
git commit -m "feat(auth): add OAuth provider support"
```

### 3. Create Pull Request

1. Push your branch: `git push origin feature/your-feature-name`
2. Create PR targeting `weekly` branch
3. Use conventional commit in title:
   - `feat:` - New features
   - `fix:` - Bug fixes
   - `docs:` - Documentation changes
   - `test:` - Test changes
   - `refactor:` - Code restructuring

### 4. Code Review

- Address review feedback
- Ensure tests pass
- Wait for maintainer approval

## Code Review Checklist

### Before Submitting a PR

- [ ] All tests pass locally (`poetry run python tests/run_tests.py all`)
- [ ] Code follows [STYLE-GUIDE.md](STYLE-GUIDE.md)
- [ ] Documentation is updated (docstrings, relevant docs)
- [ ] Commit messages follow conventional commit format
- [ ] No secrets or credentials in code
- [ ] New features have corresponding tests

### Review Focus Areas

When reviewing or when preparing your PR for review:

- **Security**: Check for potential vulnerabilities
- **Performance**: Look for inefficient operations
- **Maintainability**: Ensure code is readable and well-structured
- **Testing**: Verify adequate test coverage
- **Documentation**: Confirm docs match implementation

## Commit Message Format

```
type(scope): description

# Examples
feat(api): add circle management endpoints
fix(storage): resolve PostgreSQL connection timeout
docs(auth): update OAuth configuration examples
refactor(common): extract ID generation to utils module
test(integration): add user flow tests
```

## Testing

Always run tests before committing:

```bash
# All tests
poetry run python tests/run_tests.py all

# Specific category
poetry run python tests/run_tests.py unit
poetry run python tests/run_tests.py integration
```

See [TESTING-GUIDE.md](TESTING-GUIDE.md) for complete testing documentation.

## Pre-Push Hooks (Recommended)

Set up the pre-push hook to catch issues early:

```bash
git config core.hooksPath .githooks
```

The hook runs sanity checks before allowing pushes. To bypass (not recommended): `git push --no-verify`

## Maintainer Workflow

### Weekly → Staging

After sprint review:
1. Create PR: `weekly` → `staging`
2. Title: `"T3W10: weekly PR"` (or appropriate week)
3. Validate on staging environment

### Staging → Main

After staging validation:
1. Create PR: `staging` → `main`
2. Title: `"v0.2.0: staging PR"`
3. Tag release after merge

## Development Guidelines

For code-level guidelines (patterns, architecture, imports), see:
- [development-guidelines.md](development-guidelines.md) - Architecture patterns
- [STYLE-GUIDE.md](STYLE-GUIDE.md) - Code standards and import patterns
- [architecture.md](architecture.md) - System design

## Getting Help

- **[Issues](https://github.com/nyjc-computing/campus/issues)** - Bug reports and feature requests
- **[Discussions](https://github.com/nyjc-computing/campus/discussions)** - Questions
- **[Code Reviews](https://nyjc-computing.github.io/nanyang-system-developers/contributors/training/code-reviews.html)** - Best practices

---

**Ready to contribute?** Create your feature branch from `weekly` and start building! 🚀
