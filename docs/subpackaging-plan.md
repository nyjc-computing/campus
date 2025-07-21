# Subpackaging Implementation Plan

## Goal
Transform the Campus monorepo into independently distributable packages while maintaining the single-repository development experience.

## Package Architecture

### Target Packages (7 total)
- **campus-common**: Shared utilities (no dependencies)
- **campus-vault**: Secure secrets management (depends on common)
- **campus-client**: External API integrations (depends on common)
- **campus-models**: Data models and schemas (depends on common)
- **campus-storage**: Storage interfaces/backends (depends on common + vault)
- **campus-apps**: Web applications (depends on all others)
- **campus-workspace**: Full deployment package (depends on all others)

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

### ⏳ **Phase 3: Development Distribution** (Next)
- **Git-based distribution**: External projects use git dependencies during development
- **Branch stability**: Maintain stable development branches for external consumption
- **Documentation**: Installation guides for git-based dependencies
- **Testing framework**: Validate packages work in external projects

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

## Current Status: Ready for External Distribution 🚀

**All infrastructure work complete.** Packages are independently buildable, tested, and documented with proven architectural patterns.

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

### Next Steps for Phase 3
1. **Set up stability branches** (stable, dev, nightly) (1 day)
2. **Create git dependency templates** for external projects (1 day)
3. **Test external usage** with git dependencies (1 day)
4. **Document branch policies** and update workflows (1 day)

### Git Dependency Patterns for External Projects

**Stable Dependencies (Recommended):**
```toml
# All packages from same stability branch - guaranteed compatibility
[tool.poetry.dependencies]
campus-vault = {git = "https://github.com/nyjc-computing/campus.git", subdirectory = "campus/vault", branch = "stable"}
campus-common = {git = "https://github.com/nyjc-computing/campus.git", subdirectory = "campus/common", branch = "stable"}
```

**Development Dependencies:**
```toml
# Latest features for development/testing
[tool.poetry.group.dev.dependencies]
campus-vault = {git = "https://github.com/nyjc-computing/campus.git", subdirectory = "campus/vault", branch = "dev"}
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
