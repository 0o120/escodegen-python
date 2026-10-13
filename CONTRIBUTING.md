# Contributing

Use Python 3.11+ and Node 24+ for the ECMAScript 2026 verification corpus.
Node is required only to develop/test the package, not to generate code.

Install the sibling utility and parser checkouts before this package to test
the coordinated source changes without relying on published versions:

```sh
python -m venv .venv
# Activate .venv with the command appropriate to your shell.
python -m pip install -r requirements-dev.txt
python -m pip install -e ../esutils-python
python -m pip install -e ../esprima-python
python -m pip install -e .
npm ci --prefix tools/reference --ignore-scripts
python -W error -m compileall -q -f escodegen
python -m unittest discover -s tests -v
python -m build
python -m twine check --strict dist/*
python tools/check_distribution.py
```

Tests explicitly mark independent-oracle tests unavailable if Node or the
locked oracle dependencies are absent. CI installs both and runs every test.
`ESCODEGEN_REFERENCE_NODE_MODULES` can select a shared oracle directory.
Add minimal regression tests for defects and runtime checks for escaping,
directives, restricted productions and branch attachment. AST comparison
must retain async/await/optional, BigInt and module metadata.

Make focused commits for major repairs or feature groups. Preserve upstream
licenses and report attribution. Build source archives/wheels, then build a
wheel from the source archive and smoke-test an isolated coordinated install.

GitHub Actions checks compatible sibling sources: the coordinated modernization
branch during its review and `master` for normal development and releases,
with a manual `dependency-ref` override for integration checks. The full Python
matrix runs on Windows/Linux, with a macOS smoke job, and validates packaged
README examples against extracted wheels.

After a push to `master` passes the entire matrix, the publishing workflow
uploads a new declared stable version using the repository Actions secret.
Already-published versions are skipped. See [RELEASING.md](RELEASING.md) for
version bumps, dependency release order and interrupted-upload recovery.
