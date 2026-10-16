#!/usr/bin/env python3
"""Reproduce the verified two-voice pack with normalized archive metadata."""
import argparse
import gzip
import hashlib
import json
import tarfile
from pathlib import Path
from build_kokoro_resources import ensure, validate

TAG = 'kokoro-fp32-michael-heart-v1'
ASSET = TAG + '.tar.gz'

def package(source, output):
    validate(source)
    expected = json.loads(Path(__file__).with_name('kokoro_release_files.json').read_text())
    actual = {p.relative_to(source).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in source.rglob('*') if p.is_file() and p.name != '.gtl-kokoro-ready'}
    if actual != expected:
        changed = sorted(name for name in set(actual) | set(expected) if actual.get(name) != expected.get(name))
        raise ValueError('Pack differs from tested files: ' + ', '.join(changed))
    output.mkdir(parents=True, exist_ok=True)
    archive = output / ASSET
    # Only required files and complete upstream notices/resources are included.
    # Normalize file metadata; the publisher also pins its compression output.
    with archive.open('wb') as raw, gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0, compresslevel=6) as compressed:
        with tarfile.open(fileobj=compressed, mode='w|', format=tarfile.USTAR_FORMAT) as stream:
            for path in sorted(source.rglob('*'), key=lambda p: p.relative_to(source).as_posix()):
                if not path.is_file() or path.name == '.gtl-kokoro-ready':
                    continue
                if path.is_symlink():
                    raise ValueError('Symlinks are not allowed in a model release')
                name = 'FreeReadingKokoro/' + path.relative_to(source).as_posix()
                info = tarfile.TarInfo(name)
                info.size = path.stat().st_size
                info.mode = 0o644
                info.mtime = 0
                with path.open('rb') as content:
                    stream.addfile(info, content)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (output / (ASSET + '.sha256')).write_text(digest + '  ' + ASSET + '\n')
    manifest = {'tag': TAG, 'asset': ASSET, 'sha256': digest, 'bytes': archive.stat().st_size}
    (output / 'release-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest), flush=True)
    return archive

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--source-pack', type=Path)
    args = parser.parse_args()
    package(args.source_pack if args.source_pack else ensure(args.cache), args.output)

if __name__ == '__main__':
    main()
