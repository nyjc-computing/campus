# Subpackaging Implementation Plan

## Goal
Transform the Campus monorepo into independently distributable packages while maintaining the single-repository development experience.

## Package Architecture

### Target Packages (7 total)
- **campus-suite-common**: Shared utilities (no dependencies)
- **campus-suite-vault**: Secure secrets management (depends on common)
- **campus-suite-client**: External API integrations (depends on common)
- **campus-suite-models**: Data models and schemas (depends on common)
- **campus-suite-storage**: Storage interfaces/backends (depends on common + vault)
- **campus-suite-apps**: Web applications (depends on all others)
- **campus-suite-workspace**: Full deployment package (depends on all others)

### Dependency Flow
```
apps, workspace ──┐
                  ▼
         ┌─── storage ───┐
         ▼               ▼
    vault, client,   common
    models ──────────────┘
```

## Implementation Status

### ✅ **Phase 1: Structure & Isolation** (Completed)
- **Namespace packages**: All modules under `campus.*` namespace
- **Package files**: 7 independent `pyproject.toml` files created
- **Circular dependencies**: Resolved by moving shared components to `campus.common`
- **Build independence**: All packages build successfully in isolation
- **Import safety**: Fixed stdlib shadowing (`collections` → `documents`)

### ✅ **Phase 2: CI/CD & Architecture** (Completed) 
- **Automated testing**: Comprehensive CI/CD pipeline validates all packages
- **Lazy loading**: External resources (DB, vault) defer connection until needed
- **Build isolation**: Packages build without production secrets
- **Development guidelines**: Architectural patterns documented
- **Quality assurance**: Dependency ordering enforced

### ✅ **Phase 3: Development Distribution** (Completed)
- **Git-based distribution**: External projects use git dependencies during development
- **Branch stability**: Three-branch educational model implemented (weekly → staging → main)
- **Documentation**: Comprehensive PACKAGING.md guide created
- **Testing framework**: Packages available via git dependencies from main branch

## Key Achievements

### Critical Issues Resolved
1. **Circular Dependencies**: Moved `campus.apps.errors` and `campus.apps.webauth` to `campus.common`
2. **Import Shadowing**: Renamed `collections/` to `documents/` to avoid Python stdlib conflicts  
3. **Build Failures**: Implemented lazy loading pattern for database connections
4. **CI/CD Reliability**: Standardized Poetry configuration and dependency ordering
5. **Version Inconsistencies**: Aligned pymongo versions across all packages (^4.13.2)

### Architectural Patterns Established
- **Lazy Loading**: External resources loaded only when needed ([docs/development-guidelines.md](development-guidelines.md))
- **Vault-Centralized Config**: All environment variables accessed through vault system
- **Interface-First Design**: Abstract interfaces before concrete implementations
- **Environment Isolation**: Build-time separation from runtime dependencies

## Current Status: Campus Suite Ready for Production! 🎉

**All phases complete.** The Campus Suite is now available as 7 independent packages via git dependencies with a proven three-branch educational workflow.

### ✅ Branch Structure Implemented
```bash
git branch -a | grep -E "(weekly|staging|main)"
# weekly  - Active student development
# staging - Extended testing & validation  
# main    - Production stable packages
```

### ✅ Git Dependencies Available
```bash
# Install stable packages from main
pip install git+https://github.com/nyjc-computing/campus.git#subdirectory=campus/vault&branch=main
pip install git+https://github.com/nyjc-computing/campus.git#subdirectory=campus/common&branch=main

# Or use Poetry
poetry add git+https://github.com/nyjc-computing/campus.git#subdirectory=campus/vault&branch=main
```

### ✅ Documentation Complete
- **PACKAGING.md**: Comprehensive guide for all packaging operations
- **CONTRIBUTING.md**: New developer onboarding workflows  
- **development-guidelines.md**: Architectural patterns and best practices

### Validation Commands
```bash
# Test all packages build independently
cd campus/common && poetry build    # ✅ Works
cd campus/vault && poetry build     # ✅ Works  
cd campus/storage && poetry build   # ✅ Works
# ... all 7 packages working

# CI/CD validates every commit
# See: .github/workflows/package-testing.yml
```

### Next Steps for Phase 4 (Future)
1. **External validation** - Test with real external projects (as needed)
2. **PyPI migration planning** - Prepare for eventual PyPI publishing (6-12 months)
3. **Advanced automation** - Enhanced CI/CD for branch promotions (as needed)
4. **Performance optimization** - Monitor git dependency performance in practice

### Branch Strategy

**Simple Three-Branch Model:**
```
weekly → staging → main
   ↑        ↑
campus-subpackaging (current work, will become weekly)
```

**Branch Purpose:**
- **`main`** - Stable, production-ready packages for external projects
- **`staging`** - Extended testing, migration validation, pre-production
- **`weekly`** - Active development, student work, expected breakage

**Flow:**
- `campus-subpackaging` → `weekly` (rename current branch)
- `weekly` → `staging` (promote after weekly sprint testing)
- `staging` → `main` (promote after extended validation)

**GitHub Default:** `main` (users get stable packages by default)

### Git Dependency Patterns for External Projects

**Stable Dependencies (Recommended):**
```toml
# All packages from main branch - stable, tested versions
[tool.poetry.dependencies]
campus-suite-vault = {git = "https://github.com/nyjc-computing/campus.git", subdirectory = "campus/vault", branch = "main"}
campus-suite-common = {git = "https://github.com/nyjc-computing/campus.git", subdirectory = "campus/common", branch = "main"}
```

**Development Dependencies:**
```toml
# Latest features for development/testing
[tool.poetry.group.dev.dependencies]
campus-suite-vault = {git = "https://github.com/nyjc-computing/campus.git", subdirectory = "campus/vault", branch = "staging"}
```

**Why This Works:**
- ✅ **Dependency compatibility** - All packages from same branch work together
- ✅ **Simple maintenance** - No individual package version coordination
- ✅ **Clear stability levels** - Users choose their risk/feature balance
- ✅ **Realistic scope** - Matches how monorepo packages actually depend on each other

### Reference Documentation
- **Development Patterns**: [development-guidelines.md](development-guidelines.md)
- **Package Architecture**: [packaging-architecture.md](packaging-architecture.md)  
- **Build Progress**: [campus-client-branch-progress.md](campus-client-branch-progress.md)
- **Git Dependencies**: [git-dependencies-guide.md](git-dependencies-guide.md)

---

**Success Metrics**: ✅ Independent builds | ✅ CI/CD automation | ✅ Lazy loading | ✅ Documentation | ⏳ Git distribution
