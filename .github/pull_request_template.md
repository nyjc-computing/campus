<!--
Every PR links its related issue when one exists. PRs merge into `weekly`,
so closing keywords do not auto-close issues — the issue is closed manually
after merge, with verification.
-->

## Issue

<!-- Required when one exists: "Fixes #N" or "Refs #N". -->

## Summary

<!-- What changed and why. -->

## Repro

### Before

<!-- The command/request (and its output) that demonstrated the bug. -->

### After

<!-- The same command/request after this change. -->

## Testing

- [ ] Unit tests pass (`poetry run python tests/run_tests.py unit`)
- [ ] Integration tests pass (`poetry run python tests/run_tests.py integration`)
- [ ] Contract suite checked (`poetry run python tests/run_tests.py contract`) — must stay green; if a skip was removed, the linked issue is fixed and should be closed after merge
