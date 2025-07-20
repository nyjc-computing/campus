# Campus Client Branch Progress

This document tracks the progress of multiple PRs within the campus-client branch.

## Overview

The campus-client branch contains several improvements to the campus client system:
1. Specifying base URLs for different deployments
2. Module organization for scalability
3. API alignment between client and server
4. Documentation improvements
5. Migration from campus.vault to campus.client

## PR 1: Specifying Base URLs

**Status:** Not Started
**Goal:** Configure proper base URLs for different deployments

### Current State
- campus.apps deployed at: `api.campus.nyjc.dev`
- campus.vault deployed at: `vault.campus.nyjc.dev`
- Both accessed through campus.client namespace

### Requirements
- Simple hardcoded base URL configuration
- Separate URL handling for apps vs vault resources

### Files to Modify
- [ ] `campus/client/base.py` - Base URL configuration
- [ ] `campus/client/circles.py` - Apps-based resources
- [ ] `campus/client/users.py` - Apps-based resources  
- [ ] `campus/client/vault*.py` - Vault-based resources

---

## PR 2: Module Organization

**Status:** Not Started
**Goal:** Improve organization for many client resources

### Current State
- Flat file structure in `campus/client/`
- Individual files for each resource type

### Analysis Needed
- Review current structure
- Design scalable organization pattern
- Consider subresource grouping

---

## PR 3: API Alignment Check

**Status:** Not Started
**Goal:** Document mismatches between client and server APIs

### Analysis Required
- Compare campus.client resource names vs campus.apps
- Compare campus.client paths vs campus.vault
- Document parameter mismatches
- **Note:** No implementation changes, documentation only

---

## PR 4: Documentation

**Status:** Not Started
**Goal:** Create comprehensive documentation

### Deliverables
- [ ] Package README for campus.client
- [ ] Resource/subresource documentation
- [ ] Available verbs documentation

---

## PR 5: Refactor Migration

**Status:** Not Started
**Goal:** Migrate from campus.vault model to campus.client

### Current Issues
- campus.storage relies on campus.vault
- campus.apps relies on campus.vault
- campus.models relies on campus.vault
- Requires VAULTDB_URI environment variable
- Security concerns with current implementation

### Analysis Required
- Identify all dependencies on campus.vault
- Plan migration strategy
- Assess security improvements

---

## Commit Strategy

Work will be kept atomic with clean commits for each logical unit of work.
Progress will be tracked and commits will be made when significant milestones are reached.
