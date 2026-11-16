"""tests.fixtures

This module provides functions for setting up fixtures used in testing.

Q: What is a test fixture?
A: (ChatGPT) A **test fixture** is any fixed state of a system that is set up
as a baseline for running tests.

In other words, it’s the **preparation work** you do before executing tests, so
that your tests can run against a known, controlled environment. This usually
includes:

* **Creating necessary data** (e.g., dummy objects, sample database records).
* **Configuring the environment** (e.g., setting environment variables, mocking services).
* **Initializing dependencies** (e.g., starting a temporary server, loading a config file).
* **Cleaning up afterward** (e.g., deleting files, tearing down database tables).

## General guidelines

- Minimise global imports of campus packages
- Use fixtures to set up and tear down test environments
- Keep tests isolated and independent
- Use descriptive names for fixtures and tests
- Document the purpose and usage of fixtures
"""
