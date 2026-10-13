"""Read-only PyPI preflight and verified upload staging; never uploads files."""
import argparse
import ast
from email import message_from_bytes
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import tarfile
import tomllib
from urllib.error import HTTPError, URLError
from urllib.request import urlopen
import zipfile

from packaging.requirements import Requirement
from packaging.markers import Marker
from packaging.specifiers import SpecifierSet
from packaging.version import InvalidVersion, Version


def normalized(name):
    if not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?', name):
        raise ValueError('Invalid distribution name')
    return re.sub(r'[-_.]+', '-', name).lower()


def declaration(root, expected):
    config = tomllib.loads((root / 'pyproject.toml').read_text(encoding='utf-8'))
    project = config['project']
    name = normalized(project['name'])
    if name != normalized(expected):
        raise ValueError('Project name differs from the workflow PyPI target')
    value = project.get('version')
    if value is None:
        source = (root / config['tool']['hatch']['version']['path']).resolve()
        if not source.is_relative_to(root.resolve()):
            raise ValueError('Version source must be inside the checkout')
        for item in ast.parse(source.read_text(encoding='utf-8')).body:
            if isinstance(item, ast.Assign) and any(isinstance(target, ast.Name) and target.id == '__version__' for target in item.targets):
                value = ast.literal_eval(item.value)
                break
    if not isinstance(value, str):
        raise ValueError('The declared version must be a literal string')
    version = Version(value)
    if version.is_prerelease or version.is_devrelease or version.local or str(version) != value:
        raise ValueError('Publishing requires a canonical stable PEP 440 version')
    return name, value, project


def get_json(api, path):
    try:
        with urlopen(api.rstrip('/') + '/' + path, timeout=30) as response:
            return json.load(response)
    except HTTPError as error:
        if error.code == 404:
            return None
        raise ValueError('PyPI lookup returned HTTP ' + str(error.code) + '; publishing is blocked') from None
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        raise ValueError('PyPI lookup failed; publishing is blocked') from error


def filenames(name, version):
    prefix = name.replace('-', '_') + '-' + version
    return prefix + '-py3-none-any.whl', prefix + '.tar.gz'


def remote_release(api, name, version):
    result = get_json(api, name + '/' + version + '/json')
    if result is not None:
        if normalized(result['info']['name']) != name or Version(result['info']['version']) != Version(version):
            raise ValueError('PyPI returned metadata for a different release')
    return result


def plan(root, expected, api):
    name, version, project = declaration(root, expected)
    existing = remote_release(api, name, version)
    names = {item['filename'] for item in existing['urls']} if existing else set()
    complete = set(filenames(name, version)).issubset(names)
    if complete:
        message = name + ' ' + version + ' is already published. Bump the declared version to release further changes.'
    else:
        current = get_json(api, name + '/json')
        stable = []
        for value, files in (current or {}).get('releases', {}).items():
            try:
                candidate = Version(value)
            except InvalidVersion:
                continue
            if files and not candidate.is_prerelease and not candidate.is_devrelease:
                stable.append(candidate)
        if stable and Version(version) < max(stable):
            raise ValueError('Declared version is older than the latest stable PyPI release')
        message = ('Resume incomplete release ' if existing else 'Prepare new release ') + name + ' ' + version
    return {'project': name, 'version': version, 'publish': not complete,
            'status': 'published' if complete else 'partial' if existing else 'new', 'message': message}


def requirement_key(requirement):
    return (normalized(requirement.name), frozenset(normalized(extra) for extra in requirement.extras),
            str(requirement.specifier), requirement.url, str(requirement.marker) if requirement.marker else None)


def expected_requirements(project):
    result = {requirement_key(Requirement(text)) for text in project.get('dependencies', [])}
    for extra, requirements in project.get('optional-dependencies', {}).items():
        for text in requirements:
            requirement = Requirement(text)
            condition = 'extra == "' + normalized(extra) + '"'
            requirement.marker = Marker('(' + str(requirement.marker) + ') and ' + condition if requirement.marker else condition)
            result.add(requirement_key(requirement))
    return result


def check_metadata(metadata, name, version, project):
    if normalized(metadata['Name']) != name or metadata['Version'] != version:
        raise ValueError('Built artifact project/version differs from the declared release')
    if not metadata['Requires-Python'] or SpecifierSet(metadata['Requires-Python']) != SpecifierSet(project['requires-python']):
        raise ValueError('Built Python requirement differs from pyproject.toml')
    actual = {requirement_key(Requirement(text)) for text in metadata.get_all('Requires-Dist', [])}
    if actual != expected_requirements(project):
        raise ValueError('Built dependencies/extras differ from pyproject.toml')


def runtime_dependencies_ready(api, metadata):
    for text in metadata.get_all('Requires-Dist', []):
        requirement = Requirement(text)
        if requirement.marker and not requirement.marker.evaluate({'extra': ''}):
            continue
        package = get_json(api, normalized(requirement.name) + '/json')
        available = False
        for text, files in (package or {}).get('releases', {}).items():
            try:
                version = Version(text)
            except InvalidVersion:
                continue
            if requirement.specifier.contains(version, prereleases=False) and any(not item.get('yanked', False) for item in files):
                available = True
                break
        if not available:
            raise ValueError('Required dependency is not released on PyPI: ' + str(requirement) + '. Release it first, then rerun this publishing workflow.')


def stage(root, expected, expected_version, api, dist, output):
    name, version, project = declaration(root, expected)
    if version != expected_version:
        raise ValueError('Declared version changed after the publishing preflight')
    wanted_wheel, wanted_source = filenames(name, version)
    wheels, sources = list(dist.glob('*.whl')), list(dist.glob('*.tar.gz'))
    if len(wheels) != 1 or len(sources) != 1 or wheels[0].name != wanted_wheel or sources[0].name != wanted_source:
        raise ValueError('Expected exactly one correctly named pure Python wheel and source archive')
    with zipfile.ZipFile(wheels[0]) as archive:
        entries = [name for name in archive.namelist() if name.endswith('.dist-info/METADATA')]
        if len(entries) != 1:
            raise ValueError('Expected one wheel metadata record')
        metadata = message_from_bytes(archive.read(entries[0]))
        check_metadata(metadata, name, version, project)
        wheel_metadata = message_from_bytes(archive.read(entries[0].replace('/METADATA', '/WHEEL')))
        if wheel_metadata['Root-Is-Purelib'] != 'true' or wheel_metadata['Tag'] != 'py3-none-any':
            raise ValueError('Expected a universal pure Python wheel')
    with tarfile.open(sources[0], 'r:gz') as archive:
        entries = [item for item in archive.getmembers() if len(Path(item.name).parts) == 2 and item.name.endswith('/PKG-INFO')]
        if len(entries) != 1:
            raise ValueError('Expected one source archive metadata record')
        check_metadata(message_from_bytes(archive.extractfile(entries[0]).read()), name, version, project)
    runtime_dependencies_ready(api, metadata)
    existing = remote_release(api, name, version)
    published = {item['filename']: item for item in existing['urls']} if existing else {}
    selected = []
    for path in (wheels[0], sources[0]):
        checksum = sha256(path.read_bytes()).hexdigest()
        if path.name in published:
            if published[path.name].get('digests', {}).get('sha256') != checksum:
                raise ValueError('Existing PyPI file differs: ' + path.name + '. PyPI files cannot be overwritten; declare a new version.')
        else:
            selected.append(path)
    if output.exists() and any(output.iterdir()):
        raise ValueError('Upload staging directory must be empty')
    output.mkdir(parents=True, exist_ok=True)
    for path in selected:
        shutil.copyfile(path, output / path.name)
    return {'project': name, 'version': version, 'publish': bool(selected),
            'files': [path.name for path in selected], 'message': 'Verified upload artifacts; existing identical files are preserved.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('plan', 'stage'))
    parser.add_argument('--project', required=True)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--api-root', default='https://pypi.org/pypi')
    parser.add_argument('--version')
    parser.add_argument('--dist', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.operation == 'plan':
        result = plan(args.root, args.project, args.api_root)
    else:
        if args.version is None or args.dist is None or args.output is None:
            parser.error('stage requires --version, --dist and --output')
        result = stage(args.root, args.project, args.version, args.api_root, args.dist, args.output)
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as stream:
            stream.write('publish=' + str(result['publish']).lower() + '\nversion=' + result['version'] + '\n')
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as stream:
            stream.write(result['message'] + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
