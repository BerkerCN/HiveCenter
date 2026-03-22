# Contributing to HiveCenter

Thank you for your interest in contributing to HiveCenter. This document provides guidelines for submitting issues, feature requests, and pull requests to the project.

## Code of Conduct

By participating in this project, you agree to abide by the [Code of Conduct](CODE_OF_CONDUCT.md). Please report any unacceptable behavior to the project maintainers.

## Issue Reporting

When filing an issue, please ensure you include:
- A clear, descriptive title.
- The environment configuration (OS, Python version, utilized models).
- Exact steps necessary to reproduce the behavior.
- Relevant system logs or stack traces.

## Development Workflow

### Local Setup
1. Fork the repository and create your feature branch: `git checkout -b feature/my-feature`
2. Install dependencies: `make install` (runtime) and `make install-dev` (adds pytest and other dev pins from `requirements-dev.txt`).
3. Implement your feature or bug fix.

### Testing and Linting
All modifications must pass the continuous integration pipeline before review.
- Run `make test` (pytest) and `make lint` (flake8: syntax and critical issues) before opening a PR.
- New behavior should include or update tests under `tests/` when practical.

## Pull Requests

1. Read the `PULL_REQUEST_TEMPLATE.md` thoroughly.
2. Outline the rationale and architectural impact of your changes.
3. Submit the Pull Request against the `main` branch.
4. Maintainers will review the code for security impacts and stability prior to merging.

Your time and contributions to improving the framework's stability are highly appreciated.
