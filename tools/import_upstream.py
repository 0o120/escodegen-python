"""Refresh upstream syntax fixtures from the pinned escodegen 2.1.0 archive."""
import hashlib
import io
import json
from pathlib import Path
import tarfile
import urllib.request

URL = 'https://codeload.github.com/estools/escodegen/tar.gz/refs/tags/v2.1.0'
DESTINATION = Path(__file__).resolve().parents[1] / 'tests' / 'upstream'
DIRECTORIES = {'compare', 'compare-acorn-es6', 'compare-acorn-es7', 'compare-acorn-es2019',
               'compare-acorn-es2020', 'compare-acorn-es2021', 'compare-esprima2',
               'compare-fixed-harmony', 'compare-harmony'}


def main():
    archive = urllib.request.urlopen(URL).read()
    DESTINATION.mkdir(parents=True, exist_ok=True)
    count = 0
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as tar:
        for member in tar.getmembers():
            parts = Path(member.name).parts
            if len(parts) == 4 and parts[1] == 'test' and parts[2] in DIRECTORIES and member.isfile():
                relative = Path(parts[2]) / parts[3]
                destination = DESTINATION / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(tar.extractfile(member).read())
                count += 1
            elif len(parts) == 2 and parts[1] == 'LICENSE.BSD':
                (DESTINATION / 'LICENSE.BSD').write_bytes(tar.extractfile(member).read())
    (DESTINATION / 'PROVENANCE.json').write_text(json.dumps({
        'upstream': 'https://github.com/estools/escodegen', 'release': '2.1.0',
        'archive': URL, 'sha256': hashlib.sha256(archive).hexdigest(), 'fixture_files': count,
        'scope': 'All comparison corpus files for standard ECMAScript syntax; Mozilla extensions excluded.'
    }, indent=2) + '\n')
    print(f'Imported {count} fixture files')


if __name__ == '__main__':
    main()
