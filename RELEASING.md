# Publishing escodegen

The initial modern stable release is **2.0.0**, requiring **Python 3.11+**.
The PyPI distribution is `escodegen`; the import remains `escodegen`.

## Automatic publishing

Every push to `master` runs the full existing `Tests and package builds` workflow. When its entire
matrix passes, `.github/workflows/pypi.yml` checks out that exact tested commit,
checks the declared stable version, builds the source archive and a wheel from
it, validates both, and publishes a new version to
[PyPI](https://pypi.org/project/escodegen/).

Publishing uses the repository's `PYPI_API_TOKEN` Actions secret. Credentials
are used only in a separate upload job; they are never part of source files or
build artifacts. Actions are pinned to commit hashes. Pull requests and other
branches run their normal checks and do not publish.

## Make the next release

1. Update `__version__` in `escodegen/__init__.py` to a new stable PEP 440 version.
   `pyproject.toml` obtains its version from that file; keep this single source.
2. Update the changelog, README and compatibility/dependency ranges as needed.
3. Push or merge the changes to `master`. Publishing follows successful CI.

An ordinary push with an already-published version is skipped with an explicit
summary. PyPI files cannot be overwritten: a version bump is required to
publish further changes. Prereleases, development versions, local versions,
wrong artifact names/metadata and unavailable runtime dependencies are blocked.
Release jobs are queued rather than cancelled by another publishing run.

For an interrupted upload, rerun the failed publishing workflow after resolving
the error. Already-uploaded files must match the newly built SHA256 exactly;
only missing files are uploaded. A conflicting file requires a new version.
PyPI lookup errors block publishing rather than pretending a version is absent.

## Coordinated dependency updates

Integration CI checks compatible sibling sources together. For coordinated
changes, make the matching sibling revisions available before relying on the
full integration result. If a check ran before a required sibling update,
rerun its original push CI run once that update is available. A successful
rerun triggers publication for a new declared version.

Publish `esutils 2.0.0` before `escodegen 2.0.0`, which requires `esutils>=2,<3`.
Parser and walker do not need a sibling runtime release. If the generator's
dependency is not yet on PyPI, its upload staging fails with a clear message;
rerun that publishing workflow after the utility release becomes available.

The new metadata and README appear on PyPI after the first successful upload.
Existing PyPI releases remain available for users of the earlier Python floor.

## Local package checks

Install the project's pinned development/build requirements, then run:

The generator's extracted-wheel README checks also need the compatible parser
and utility libraries. In the coordinated workspace, first run
`python -m pip install ../esutils-python ../esprima-python`; see
[CONTRIBUTING.md](CONTRIBUTING.md) for dependency setup.

```console
python -m build --no-isolation
python -m twine check --strict dist/*
python tools/check_distribution.py
python tools/pypi_release.py plan --project escodegen
```

The preflight/staging helper only reads PyPI metadata and prepares local files;
it cannot upload anything.

See [PyPA's publishing action](https://github.com/pypa/gh-action-pypi-publish)
and [GitHub workflow_run](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_run)
for the publishing job and CI-completion trigger.
