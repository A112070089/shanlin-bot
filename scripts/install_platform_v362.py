"""Add-only, idempotent, fail-closed v3.6.2 local test patch installer."""
from __future__ import annotations
import argparse
import ast
import os
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
FILES = (
    'website/integrated_app_platform_v362.py',
    'website/platform_shanlin_booking_source_v362.py',
    'website/platform_shanlin_booking_routes_v362.py',
    'sandbox/shanlin_v362_source_router.py',
    'sandbox/shanlin_v362_sandbox_app.py',
    'tests/test_platform_booking_v362.py',
    'scripts/install_platform_v362.py',
)
REQUIRED = (
    'website/integrated_app_platform_v361.py',
    'website/platform_shanlin_booking_routes_v361.py',
    'website/pilot_backend.py',
    'website/platform_console.py',
    'sandbox/shanlin_readonly_sandbox_v361.py',
    'tests/test_platform_booking_v361.py',
)


def inspect(root: Path):
    errors, actions = [], []
    for rel in REQUIRED:
        item = root / rel
        if not item.is_file():
            errors.append('Missing prerequisite: ' + rel)
        elif rel.endswith('.py'):
            try: ast.parse(item.read_text(encoding='utf-8'))
            except (SyntaxError,OSError,UnicodeError):
                errors.append('Invalid prerequisite Python: '+rel)
    for rel in FILES:
        src = PACKAGE / rel
        dst = root / rel
        if not src.is_file():
            errors.append('Package missing: '+rel)
        elif dst.exists():
            if not dst.is_file() or dst.read_bytes() != src.read_bytes():
                errors.append('Refusing to overwrite differing file: '+rel)
            else:
                actions.append('Already identical: '+rel)
        else:
            actions.append('Would add: '+rel)
    return errors, actions


def apply(root: Path):
    errors, actions = inspect(root)
    if errors:
        return errors, actions
    created = []
    try:
        for rel in FILES:
            src = PACKAGE / rel
            dst = root / rel
            if dst.exists():
                continue
            dst.parent.mkdir(parents=True,exist_ok=True)
            fd = os.open(dst,os.O_WRONLY | os.O_CREAT | os.O_EXCL,0o644)
            created.append(dst)
            with os.fdopen(fd,'wb') as out:
                out.write(src.read_bytes())
                out.flush()
                os.fsync(out.fileno())
    except OSError:
        for item in reversed(created):
            try: item.unlink()
            except OSError: pass
        return ['Installation failed; newly added files were rolled back'], actions
    return [], actions


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root',required=True)
    parser.add_argument('--apply',action='store_true')
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        print('STOP: project root not found')
        return 2
    errors, actions = apply(root) if args.apply else inspect(root)
    for item in actions: print(item)
    for item in errors: print('STOP:',item)
    if errors: return 2
    print('PASS: add-only, no Firebase, Railway or existing project files modified'
          if args.apply else 'PASS: preflight only')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
