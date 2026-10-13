"""Exercise release preflight/staging boundaries without credentials or uploads."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest import mock
from urllib.error import HTTPError, URLError
import zipfile


HELPER = Path(__file__).resolve().parents[1] / "tools" / "pypi_release.py"
if not HELPER.exists():
    HELPER = Path(__file__).with_name("pypi_release.py")
SPEC = importlib.util.spec_from_file_location("release_helper_under_test", HELPER)
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)

API = "https://pypi.invalid/pypi"
PROJECT = "example-release"
VERSION = "2.0.0"
WHEEL = "example_release-2.0.0-py3-none-any.whl"
SDIST = "example_release-2.0.0.tar.gz"


class PublishGuardTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.dist = self.root / "dist"
        self.upload = self.root / "upload"
        self.write_project()

    def write_project(self, version=VERSION, dependencies=(), name=PROJECT,
                      optional=None):
        text = ("[project]\nname = " + json.dumps(name)
                + "\nversion = " + json.dumps(version)
                + '\nrequires-python = ">=3.11"\ndependencies = '
                + json.dumps(list(dependencies)) + "\n")
        if optional:
            text += "[project.optional-dependencies]\n"
            for extra, requirements in optional.items():
                text += extra + " = " + json.dumps(requirements) + "\n"
        (self.root / "pyproject.toml").write_text(text, encoding="utf-8")

    def metadata(self, dependencies=(), name=PROJECT, version=VERSION,
                 requires_python=">=3.11"):
        text = ("Metadata-Version: 2.4\nName: " + name + "\nVersion: " + version
                + "\nRequires-Python: " + requires_python
                + "\nLicense-Expression: BSD-2-Clause\n")
        text += "".join("Requires-Dist: " + item + "\n" for item in dependencies)
        return (text + "\n").encode()

    def build_artifacts(self, dependencies=(), source_dependencies=None,
                        name=PROJECT, version=VERSION, requires_python=">=3.11",
                        pure="true", tag="py3-none-any"):
        self.dist.mkdir(exist_ok=True)
        metadata = self.metadata(dependencies, name, version, requires_python)
        with zipfile.ZipFile(self.dist / WHEEL, "w") as archive:
            prefix = "example_release-2.0.0.dist-info/"
            archive.writestr(prefix + "METADATA", metadata)
            archive.writestr(prefix + "WHEEL", "Wheel-Version: 1.0\nGenerator: test\n"
                             + "Root-Is-Purelib: " + pure + "\nTag: " + tag + "\n\n")
            archive.writestr(prefix + "RECORD", "")
            archive.writestr("example_release/__init__.py", "__version__ = '2.0.0'\n")
        source_metadata = self.metadata(
            dependencies if source_dependencies is None else source_dependencies,
            name, version, requires_python)
        with tarfile.open(self.dist / SDIST, "w:gz") as archive:
            info = tarfile.TarInfo("example_release-2.0.0/PKG-INFO")
            info.size = len(source_metadata)
            archive.addfile(info, io.BytesIO(source_metadata))
        return self.dist / WHEEL, self.dist / SDIST

    def release_record(self, files):
        return {"info": {"name": PROJECT, "version": VERSION}, "urls": files}

    def remote_file(self, path):
        return {"filename": path.name,
                "digests": {"sha256": hashlib.sha256(path.read_bytes()).hexdigest()}}

    def mock_api(self, responses):
        def lookup(url, timeout):
            self.assertEqual(timeout, 30)
            self.assertTrue(url.startswith(API + "/"))
            value = responses.get(url[len(API) + 1:], 404)
            if isinstance(value, int):
                raise HTTPError(url, value, "synthetic response", {}, None)
            if isinstance(value, BaseException):
                raise value
            if isinstance(value, bytes):
                return io.BytesIO(value)
            return io.BytesIO(json.dumps(value).encode())
        patch = mock.patch.object(release, "urlopen", side_effect=lookup)
        self.addCleanup(patch.stop)
        return patch.start()

    def stage(self, expected_version=VERSION):
        return release.stage(self.root, PROJECT, expected_version, API,
                             self.dist, self.upload)

    def test_new_release_stages_both_verified_artifacts(self):
        paths = self.build_artifacts()
        self.mock_api({PROJECT + "/json": {"releases": {"1.0.0": [{}]}}})
        plan = release.plan(self.root, PROJECT, API)
        self.assertEqual((plan["publish"], plan["status"]), (True, "new"))
        result = self.stage()
        self.assertEqual(set(result["files"]), {WHEEL, SDIST})
        for path in paths:
            self.assertEqual((self.upload / path.name).read_bytes(), path.read_bytes())

    def test_new_project_404_is_allowed(self):
        self.mock_api({})
        self.assertTrue(release.plan(self.root, PROJECT, API)["publish"])

    def test_dynamic_version_is_read_without_executing_source(self):
        (self.root / "pyproject.toml").write_text(
            '[project]\nname = "example-release"\ndynamic = ["version"]\n'
            'requires-python = ">=3.11"\n[tool.hatch.version]\npath = "_version.py"\n',
            encoding="utf-8")
        (self.root / "_version.py").write_text(
            'raise RuntimeError("version module must not execute")\n'
            '__version__ = "2.0.0"\n', encoding="utf-8")
        self.mock_api({})
        self.assertEqual(release.plan(self.root, PROJECT, API)["version"], VERSION)

    def test_dynamic_version_path_cannot_escape_checkout(self):
        (self.root / "pyproject.toml").write_text(
            '[project]\nname = "example-release"\ndynamic = ["version"]\n'
            'requires-python = ">=3.11"\n[tool.hatch.version]\npath = "../_version.py"\n',
            encoding="utf-8")
        lookup = self.mock_api({})
        with self.assertRaisesRegex(ValueError, "inside"):
            release.plan(self.root, PROJECT, API)
        lookup.assert_not_called()

    def test_published_version_skips_without_reading_latest_release(self):
        lookup = self.mock_api({PROJECT + "/" + VERSION + "/json":
                               self.release_record([{"filename": WHEEL}, {"filename": SDIST}])})
        result = release.plan(self.root, PROJECT, API)
        self.assertFalse(result["publish"])
        self.assertEqual(result["status"], "published")
        self.assertIn("Bump", result["message"])
        self.assertEqual(lookup.call_count, 1)
        self.assertFalse(self.upload.exists())

    def test_stale_unpublished_version_is_blocked(self):
        self.mock_api({PROJECT + "/json": {"releases": {"3.0.0": [{}], "9.0rc1": [{}]}}})
        with self.assertRaisesRegex(ValueError, "older"):
            release.plan(self.root, PROJECT, API)

    def test_unstable_or_noncanonical_versions_are_blocked_before_network(self):
        lookup = self.mock_api({})
        for value in ("2.0.0rc1", "2.0.0.dev1", "2.0.0+local", "v2.0.0"):
            with self.subTest(version=value):
                self.write_project(version=value)
                with self.assertRaises(ValueError):
                    release.plan(self.root, PROJECT, API)
        lookup.assert_not_called()

    def test_http_500_blocks_instead_of_treating_release_as_missing(self):
        self.mock_api({PROJECT + "/" + VERSION + "/json": 500})
        with self.assertRaisesRegex(ValueError, "HTTP 500"):
            release.plan(self.root, PROJECT, API)
        self.assertFalse(self.upload.exists())

    def test_network_or_invalid_json_blocks(self):
        for response in (URLError("offline"), TimeoutError(), b"not JSON"):
            with self.subTest(response=type(response).__name__):
                with mock.patch.object(release, "urlopen", side_effect=response
                                       if isinstance(response, BaseException) else None,
                                       return_value=io.BytesIO(response)
                                       if isinstance(response, bytes) else None):
                    with self.assertRaisesRegex(ValueError, "blocked"):
                        release.plan(self.root, PROJECT, API)

    def test_partial_release_stages_only_the_missing_verified_file(self):
        wheel, source = self.build_artifacts()
        self.mock_api({PROJECT + "/" + VERSION + "/json":
                       self.release_record([self.remote_file(wheel)])})
        plan = release.plan(self.root, PROJECT, API)
        self.assertEqual((plan["status"], plan["publish"]), ("partial", True))
        result = self.stage()
        self.assertEqual(result["files"], [SDIST])
        self.assertEqual(list(self.upload.iterdir()), [self.upload / SDIST])
        self.assertEqual((self.upload / SDIST).read_bytes(), source.read_bytes())

    def test_existing_hash_conflict_blocks_all_staging(self):
        wheel, _ = self.build_artifacts()
        conflicting = self.remote_file(wheel)
        conflicting["digests"]["sha256"] = "0" * 64
        self.mock_api({PROJECT + "/" + VERSION + "/json": self.release_record([conflicting])})
        with self.assertRaisesRegex(ValueError, "cannot be overwritten"):
            self.stage()
        self.assertFalse(self.upload.exists())

    def test_identical_complete_release_stages_nothing(self):
        paths = self.build_artifacts()
        self.mock_api({PROJECT + "/" + VERSION + "/json":
                       self.release_record([self.remote_file(path) for path in paths])})
        result = self.stage()
        self.assertFalse(result["publish"])
        self.assertEqual(result["files"], [])
        self.assertEqual(list(self.upload.iterdir()), [])

    def test_declared_project_or_version_change_is_blocked(self):
        self.build_artifacts()
        lookup = self.mock_api({})
        with self.assertRaisesRegex(ValueError, "changed"):
            self.stage(expected_version="2.0.1")
        self.write_project(name="other-project")
        with self.assertRaisesRegex(ValueError, "name"):
            self.stage()
        lookup.assert_not_called()
        self.assertFalse(self.upload.exists())

    def test_wrong_artifact_metadata_blocks_before_network_or_staging(self):
        lookup = self.mock_api({})
        for change in ({"name": "other-project"}, {"version": "2.0.1"},
                       {"requires_python": ">=3.12"}):
            with self.subTest(change=change):
                self.build_artifacts(**change)
                with self.assertRaises(ValueError):
                    self.stage()
        lookup.assert_not_called()
        self.assertFalse(self.upload.exists())

    def test_wrong_filename_or_multiple_wheels_block(self):
        wheel, _ = self.build_artifacts()
        lookup = self.mock_api({})
        wrong = wheel.with_name("wrong-2.0.0-py3-none-any.whl")
        wheel.rename(wrong)
        with self.assertRaises(ValueError):
            self.stage()
        wrong.rename(wheel)
        wrong.write_bytes(wheel.read_bytes())
        with self.assertRaises(ValueError):
            self.stage()
        lookup.assert_not_called()
        self.assertFalse(self.upload.exists())

    def test_platform_wheels_are_blocked(self):
        lookup = self.mock_api({})
        for change in ({"pure": "false"}, {"tag": "cp311-cp311-win_amd64"}):
            with self.subTest(change=change):
                self.build_artifacts(**change)
                with self.assertRaisesRegex(ValueError, "universal"):
                    self.stage()
        lookup.assert_not_called()

    def test_remote_release_name_or_version_mismatch_blocks(self):
        for field, value in (("name", "other-project"), ("version", "9.0.0")):
            record = self.release_record([])
            record["info"][field] = value
            with self.subTest(field=field), mock.patch.object(
                    release, "get_json", return_value=record):
                with self.assertRaisesRegex(ValueError, "different release"):
                    release.plan(self.root, PROJECT, API)

    def test_unreleased_runtime_dependency_blocks(self):
        self.write_project(dependencies=["esutils>=2,<3"])
        self.build_artifacts(dependencies=["esutils>=2,<3"])
        self.mock_api({"esutils/json": {"releases": {
            "1.0.1": [{}], "2.0.0rc1": [{}], "2.0.0": [{"yanked": True}]}}})
        with self.assertRaisesRegex(ValueError, "Release it first"):
            self.stage()
        self.assertFalse(self.upload.exists())

    def test_released_runtime_dependency_allows_staging(self):
        self.write_project(dependencies=["esutils>=2,<3"])
        self.build_artifacts(dependencies=["esutils>=2,<3"])
        self.mock_api({"esutils/json": {"releases": {"2.0.0": [{"yanked": False}]}}})
        self.assertTrue(self.stage()["publish"])

    def test_equivalent_requirement_names_and_specifiers_allow_staging(self):
        self.write_project(dependencies=["Es.Utils >=2,<3"])
        self.build_artifacts(dependencies=["es-utils<3,>=2"])
        self.mock_api({"es-utils/json": {"releases": {"2.0.0": [{}]}}})
        self.assertTrue(self.stage()["publish"])

    def test_optional_marker_combination_matches_built_metadata(self):
        self.write_project(optional={"integration": [
            'not-yet-published>=2; python_version < "3.11" or sys_platform == "not-an-os"']})
        self.build_artifacts(dependencies=[
            'not-yet-published>=2; (python_version < "3.11" or sys_platform == "not-an-os") and extra == "integration"'])
        lookup = self.mock_api({})
        self.assertTrue(self.stage()["publish"])
        self.assertEqual(lookup.call_count, 1)

    def test_inactive_extra_does_not_block_runtime_publish(self):
        self.write_project(optional={"integration": ["not-yet-published>=2"]})
        self.build_artifacts(dependencies=['not-yet-published>=2; extra == "integration"'])
        lookup = self.mock_api({})
        self.assertTrue(self.stage()["publish"])
        self.assertEqual(lookup.call_count, 1)

    def test_dropped_declared_runtime_dependency_blocks(self):
        self.write_project(dependencies=["esutils>=2,<3"])
        self.build_artifacts()
        self.mock_api({})
        with self.assertRaises(ValueError):
            self.stage()
        self.assertFalse(self.upload.exists())

    def test_wheel_and_source_dependency_disagreement_blocks(self):
        self.write_project(dependencies=["esutils>=2,<3"])
        self.build_artifacts(dependencies=["esutils>=2,<3"], source_dependencies=[])
        self.mock_api({"esutils/json": {"releases": {"2.0.0": [{}]}}})
        with self.assertRaises(ValueError):
            self.stage()
        self.assertFalse(self.upload.exists())

    def test_staging_preserves_existing_output_files(self):
        self.build_artifacts()
        self.mock_api({})
        self.upload.mkdir()
        sentinel = self.upload / "do-not-replace.txt"
        sentinel.write_text("existing data", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "empty"):
            self.stage()
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "existing data")
        self.assertEqual(list(self.upload.iterdir()), [sentinel])


if __name__ == "__main__":
    unittest.main()
