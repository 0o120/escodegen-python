# Contributing

Use Python 3.11+ and Node 24+ for the ECMAScript 2026 verification corpus.
Node is required only to develop/test the package, not to generate code.

Install the local coordinated utility dependency before installing this
package (esutils 2 is not yet on PyPI):

```sh
python -m venv .venv
# Activate .venv with the command appropriate to your shell.
python -m pip install -r requirements-dev.txt
python -m pip install -e ../esutils-python
python -m pip install -e .
npm ci --prefix tools/reference --ignore-scripts
python -W error -m compileall -q -f escodegen
python -m unittest discover -s tests -v
python -m build
python -m twine check dist/*
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

GitHub Actions checks out the modernization esutils branch, with a manual
`dependency-ref` override. After the coordinated release, switch to its
verified release tag. Python 3.15 uses prereleases until stable is available.
Publishing packages, pushing branches and changing external PR state require
the owner's separate release instruction.
