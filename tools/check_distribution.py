"""Verify release metadata, source contents and clean-wheel README examples."""
import argparse
import ast
import email
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile

from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = config["project"]
    version_source = ROOT / config["tool"]["hatch"]["version"]["path"]
    assignments = ast.parse(version_source.read_text(encoding="utf-8")).body
    version = next(ast.literal_eval(statement.value) for statement in assignments
                   if isinstance(statement, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id == "__version__"
                           for target in statement.targets))
    wheels = list(args.dist.glob("*.whl"))
    sources = list(args.dist.glob("*.tar.gz"))
    assert len(wheels) == len(sources) == 1, "Use a clean distribution directory with one wheel and one source archive"
    with zipfile.ZipFile(wheels[0]) as archive:
        names = archive.namelist()
        metadata = email.message_from_bytes(archive.read(next(name for name in names if name.endswith("/METADATA"))))
        assert metadata["Name"] == project["name"]
        assert metadata["Version"] == version
        assert metadata["Requires-Python"] == ">=3.11"
        assert metadata["License-Expression"] == "BSD-2-Clause"
        assert metadata.get_all("License-File") == ["LICENSE"]
        assert "Development Status :: 5 - Production/Stable" in metadata.get_all("Classifier")
        assert set(metadata.get_all("Project-URL")) == {
            f"{label}, {url}" for label, url in project["urls"].items()
        }
        expected_dependencies = {str(Requirement(dependency)) for dependency in project["dependencies"]}
        for extra, dependencies in project["optional-dependencies"].items():
            expected_dependencies.update(str(Requirement(f"{dependency}; extra == {extra!r}"))
                                         for dependency in dependencies)
        assert {str(Requirement(value)) for value in metadata.get_all("Requires-Dist")} == expected_dependencies
        assert set(metadata.get_all("Provides-Extra")) == set(project["optional-dependencies"])
        assert not any("__pycache__" in name or name.startswith("tests/") for name in names)
        with tempfile.TemporaryDirectory() as folder:
            archive.extractall(folder)
            examples = re.findall(r"```python\n(.*?)```", (ROOT / "README.md").read_text(encoding="utf-8"), re.S)
            script = ("import sys\nsys.path.insert(0, sys.argv[1])\nimport escodegen\n"
                      f"assert escodegen.__version__ == {version!r}\n" + "\n".join(examples))
            subprocess.run([sys.executable, "-I", "-c", script, folder], cwd=folder, check=True)
    with tarfile.open(sources[0]) as archive:
        names = archive.getnames()
        prefix = names[0].split("/")[0]
        metadata = email.message_from_bytes(archive.extractfile(f"{prefix}/PKG-INFO").read())
        assert metadata["Version"] == version
        for name in ["README.md", "CHANGELOG.md", "CONTRIBUTING.md", "LICENSE",
                     "PERFORMANCE.md", "requirements.txt"]:
            assert f"{prefix}/{name}" in names, f"Missing source-archive documentation: {name}"
    print("Source archive, wheel metadata, clean imports and README examples verified")


if __name__ == "__main__":
    main()
