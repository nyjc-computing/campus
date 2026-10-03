---
name: pr-stacks
description: >-
  Procedure for stacked PRs and worktree-based branch surgery in this repo —
  building/rebasing PR chains, verifying unions, base retargeting, and the
  sharp edges (stack-merge tip rewrites, worktree venvs, concurrent streams).
  Use when opening, rebasing, merging, or reviewing PR stacks, when a
  worktree test run fails oddly, or before any git checkout/branch work in
  the shared checkout.
---

# PR stacks & worktree branch surgery (campus)

The rule behind everything here: **the main checkout stays on `weekly` and
only ever takes `git pull`** — concurrent agent sessions and humans share
it, and switching its branch under another stream misplaces that stream's
next commit. Details and rationale: `docs/CONTRIBUTING.md`,
"Concurrent Work Streams (Worktrees)" and "Stacked PRs".

## 1. Never touch branches in the shared checkout

- Any branch work (new branch, rebase, checkout) happens in its own
  worktree: `python scripts/worktree.py new <type>/<slug>` from the main
  checkout. Expect the ~2-minute venv build — that cost buys trustworthy
  test runs; do not "save time" with bare `git worktree add` (exFAT
  ownership errors, no venv, stub-branch litter).
- Docs-only work may pass `--no-venv`, but anything that will run
  `tests/run_tests.py` needs the venv.
- `tests/run_tests.py` refuses to run in a venv-less linked worktree and
  prints the recovery commands — that guard exists because the silent
  fallback to a system Python produced failures that looked like code bugs.
- Worktrees are single-use: `python scripts/worktree.py remove
  <type>/<slug>` after the PRs merge (branch is kept; deletion follows
  normal post-merge cleanup).
- Other streams' worktrees and uncommitted WIP are off-limits. If foreign
  modified files appear in your working tree, do NOT commit, revert, or
  stash-drop them — commit your work with explicit `git add <paths>` only,
  and surface the finding.

## 2. Building or rebuilding a stack

A stack is chained by content AND by PR base:

1. Rebase bottom-up: the bottom branch onto `origin/weekly` (fetch first),
   then each branch onto the branch below it.
2. Expect conflicts where the PRs touch the same files; resolve by union
   (both features' wiring), then verify the file compiles/imports before
   continuing the rebase.
3. Push with leases pinned to the SHAs you are replacing:
   `git push --force-with-lease=<branch>:<expected-remote-sha> origin <branch>`.
4. Retarget PR bases: `gh pr edit <n> --base <branch-below>` — the bottom
   PR keeps `weekly`. GitHub's stack-merge needs both the chained bases
   and each branch to actually contain the branch below it.
5. Verify each PR now shows exactly its own diff: `gh pr diff <n> --name-only`.

## 3. Verifying a rewritten chain

- Run type + contract (minimum) on the **tip branch** — it is the exact
  union that reaches `weekly` — in the scripted worktree:
  `.venv/Scripts/python.exe tests/run_tests.py type` / `contract`.
- CI runs per link (the workflow has no base-branch filter on
  `pull_request`), but a mid-rebase force-push sequence is only fully
  covered once pushed; the local tip run is the fast gate.
- Stacked links whose base is not `weekly` historically showed "no
  checks"; if you see that, check the PR's base and the ci.yml trigger
  comment before assuming CI is broken.

## 4. Sharp edges learned the hard way

- **GitHub's stack merge can rewrite tip commits** (new merge commits, not
  your branch heads). Before `git branch -D` on a "not fully merged"
  branch, `git diff <local-sha> <merged-sha>` to confirm identical
  content.
- **Pull local `weekly` before `git branch -d`** — post-merge deletes fail
  while the local ref is behind the merge commits.
- **`gh` argument strings execute shell backticks** — never pass bodies
  containing backticks inline; use `--body-file`.
- **Railway variables and shell state don't persist between calls** —
  fetch a secret and use it in the SAME command.
- When a merge conflict touches route/wiring files (`routes/__init__.py`,
  openapi anchors), the union is almost always the right resolution — but
  re-run the contract suite before pushing; the conflicts are exactly
  where two PRs' assumptions meet.
