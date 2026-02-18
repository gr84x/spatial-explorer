# Contributing to Spatial Explorer

Thanks for your interest in contributing.

## Getting Started

### Repo Layout

- `web/` – static browser app (vanilla JS)
- `parsers/` – Python utilities for native spatial formats
- `tests/` – Python tests for the parsers
- `marketing/` – launch/landing page materials

### Development Prerequisites

- **Node.js** (for web unit tests): Node 18+ recommended (CI uses Node 22)
- **Python** (for parser tests / lint): Python 3.9+

## Running Tests

### Web (Node)

From the repo root:

```bash
node --test web/tests/*.test.js
```

### Python

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

pytest
```

## Lint

Python linting uses **ruff**:

```bash
ruff check parsers tests
```

## Pull Request Guidelines

- Keep PRs focused and small where possible
- Add/update tests for behavioral changes
- Update docs if you change public-facing behavior
- Ensure CI is green before requesting review

## Code Style

- JavaScript: modern ES modules, no bundler required
- Python: prefer small, defensive parsing functions; optional deps should remain optional
