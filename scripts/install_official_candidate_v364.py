#!/usr/bin/env python3
"""Add-only installer of pinned Shanlin v3.6.4 security candidate (offline only).

Never updates the running platform app, Railway, Firebase, or any existing file.
Run first without --apply. No network or Firebase access.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
PINNED_PREREQS = {
    'website/integrated_app_platform_v363.py': '512d10a39190e022a9ab4834fdc583819ba32bf85400a3c67399e4a39564ef49',
    'shanlin_v363_staging/main.py': '51a6fb120b4820a73c04422c399c0dab26aeaba68403f10905a53cce4c5c3366',
    'shanlin_v363_staging/shanlin_v363_readonly.py': 'c3ac45048dd64d790e7ff5dbc87deca0f76a61c6baa9c6b8604c89592f99aab6',
}
EXTRA = ('shanlin_v364_candidate/MANIFEST.json',
         'shanlin_v364_candidate/official-to-safe-main.patch',
         'tests/test_official_candidate_v364.py',
         'scripts/install_official_candidate_v364.py')


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def payloads() -> dict[str, bytes]:
    manifest_file = PKG / 'MANIFEST.json'
    if not manifest_file.exists():
        manifest_file = PKG / 'shanlin_v364_candidate' / 'MANIFEST.json'
    manifest = json.loads(manifest_file.read_text(encoding='utf-8'))
    expected = manifest['candidate_file_sha256']
    result = {}
    for name, sha in expected.items():
        path = PKG / 'shanlin_v364_candidate' / name
        if not path.is_file() or path.is_symlink():
            raise ValueError(f'Missing file in release: {name}')
        data = path.read_bytes()
        if digest(data) != sha:
            raise ValueError(f'Corrupted candidate file: {name}')
        result[f'shanlin_v364_candidate/{name}'] = data
    for key in EXTRA:
        file = PKG / key
        if key.endswith('MANIFEST.json'):
            data = manifest_file.read_bytes()
        elif key.endswith('official-to-safe-main.patch'):
            patchfile = PKG / 'official-to-safe-main.patch'
            if not patchfile.exists():
                patchfile = PKG / 'shanlin_v364_candidate' / 'official-to-safe-main.patch'
            data = patchfile.read_bytes()
        else:
            data = file.read_bytes()
        result[key] = data
    return result


def preflight(root: Path) -> tuple[dict[str, bytes], list[str], list[str]]:
    errors,actions=[],[]
    try:
        if not root.is_dir() or root.is_symlink():
            raise ValueError('DOUBTS project root not found or symlinked')
        for rel, sha in PINNED_PREREQS.items():
            path = root / rel
            if not path.is_file() or path.is_symlink() or digest(path.read_bytes()) != sha:
                raise ValueError(f'Existing v3.6.3 source differs from reviewed snapshot: {rel}')
        content = payloads()
        for rel, data in content.items():
            target = root / rel
            if target.parent.is_symlink() or target.is_symlink():
                raise ValueError(f'Unsafe link: {rel}')
            if target.exists() and (not target.is_file() or target.read_bytes() != data):
                raise ValueError(f'Refusing to overwrite different file: {rel}')
            actions.append(('Already identical: ' if target.exists() else 'Would add: ') + rel)
        return content,errors,actions
    except (OSError,ValueError,KeyError,TypeError,json.JSONDecodeError) as exc:
        errors.append(str(exc))
        return {},errors,actions


def install(root: Path):
    content,errors,actions=preflight(root)
    if errors:
        return errors,actions
    created=[]
    try:
        for rel,raw in content.items():
            path = root / rel
            if path.exists(): continue
            path.parent.mkdir(parents=True,exist_ok=True)
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            created.append(path)
            with os.fdopen(fd,'wb') as dest:
                dest.write(raw)
                dest.flush()
                os.fsync(dest.fileno())
        return [],actions
    except OSError as exc:
        for path in reversed(created):
            path.unlink(missing_ok=True)
        return [f'Atomic add-only installation failed; created files rolled back: {exc.__class__.__name__}'],actions


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',required=True)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    root=Path(args.root).expanduser().resolve()
    errors,actions=(install(root) if args.apply else preflight(root)[1:])
    for action in actions: print(action)
    for err in errors:print('STOP:',err)
    if errors: return 2
    print('PASS: isolated candidate added; v3.6.3 website, Railway and Firebase unchanged' if args.apply
          else 'PASS: read-only preflight; no file changes')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
