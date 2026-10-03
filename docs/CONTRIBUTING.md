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

## Concurrent Work Streams (Worktrees)

Multiple agent sessions and humans share this clone. A single checkout
cannot host two branches at once — switching its branch under an active
stream makes that stream's next commit land on the wrong branch (this
caused an incident on 2026-10-03, recovered only by history surgery).
The rule is therefore:

- **The main checkout stays on `weekly`** and only ever takes `git pull`.
- **Every task runs in its own worktree** — one worktree = one branch = one PR.
- **Never `git checkout` inside another stream's worktree.**
- **Worktrees are single-use**: remove the worktree and its venv once the
  task's PRs are merged; build a fresh one for the next task. Never reuse
  a venv across tasks.

### Starting a task

```bash
python scripts/worktree.py new feat/your-feature        # code work: worktree + .venv (~2 min)
python scripts/worktree.py new docs/your-doc --no-venv  # docs-only: no venv
python scripts/worktree.py list                         # who is working where
```

The worktree is created as a sibling directory (`../campus-<slug>`) on a
new branch off `origin/weekly`. Re-running `new` with an existing branch
checks that branch out as-is (fresh venv still required — single-use
policy). Then:

```bash
cd ../campus-your-feature
.venv/Scripts/python.exe tests/run_tests.py unit    # Windows (.venv/bin/python elsewhere)
```

The script encodes the platform recipe: `D:\` is exFAT (no
junctions/symlinks; PATH tricks lose to CreateProcess search order), so
the worktree venv must be **real** — it is created from the main venv's
interpreter, filled from the main venv's `pip freeze`, and the
locally-built `campus_python` packages (not on any index) are copied
across from the main site-packages. It also registers the worktree's
`safe.directory` config.

### Finishing a task

```bash
python scripts/worktree.py remove feat/your-feature
```

Removes the worktree directory (venv included), prunes, and clears its
`safe.directory` entry. The branch is kept — branch deletion follows the
normal post-merge cleanup. `remove` refuses to discard uncommitted
changes (pass `--force-dirty` to override; untracked venv artifacts are
always ignored).

> **Always use the script, not bare `git worktree add`.** A manual
> worktree skips the `safe.directory` registration (exFAT reports
> "dubious ownership"), has no venv — and `tests/run_tests.py` then
> refuses to run rather than silently falling back to an arbitrary
> system Python — and leaves a stub branch named after the directory
> behind when removed.

### Stacked PRs

When a series of PRs belongs together, chain them: branch each PR off
the branch of the PR below it, and set each PR's base to the branch of
the PR below (the bottom PR targets `weekly` as usual). GitHub's
stack-merge then merges the chain bottom-up, surfacing each link to
`weekly` in turn. Conventions that keep this painless:

- **Each branch must contain the branch below it.** A stack where the
  links merely share a common ancestor is not mergeable as a stack.
  Rebase bottom-up: the bottom branch onto `origin/weekly`, then each
  branch onto the one below it. Push with
  `git push --force-with-lease=<branch>:<expected-sha>`.
- **CI runs per link** — the workflow has no base-branch filter on
  `pull_request`, so every stacked PR gets its own run, and a PR run
  builds head ⊕ base (exactly the content that reaches `weekly` when
  that link merges). Validate the chain tip locally too (type +
  contract at minimum) before force-pushing a rewritten chain; the
  scripted worktree's venv is what makes those runs trustworthy.
- **After a lower PR merges**, GitHub retargets the next one to
  `weekly`; if you rebase instead of using stack-merge, retarget bases
  by hand (`gh pr edit <n> --base ...`).
- **Expect tip rewrites.** GitHub's stack merge may author new merge
  commits rather than using your branch heads verbatim — before
  force-deleting a "not fully merged" local branch, diff it against
  what actually landed to confirm the content is identical.

## Workflow

### 1. Create a Worktree and Branch

```bash
# From anywhere in the repository (main checkout or another worktree)
python scripts/worktree.py new feature/your-feature-name
cd ../campus-your-feature-name
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

**Ready to contribute?** Create your task worktree from `weekly` and start building! 🚀
