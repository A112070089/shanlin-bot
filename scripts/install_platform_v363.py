"""Add-only local installation: DOUBTS platform and pinned Shanlin main.py TEST COPY.

Never writes to the source Shanlin directory, GitHub, Railway, or Firebase.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import os
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
KNOWN_SHANLIN_V352_SHA256 = '9f9c74426ceee574334eb10130b233df03aa693caef27f598dd11d8b70c6b515'
KNOWN_REMINDER_V352_SHA256 = 'fd5740d589a3eed038a6262b7ab7664418adccedc286eba5a14028e193fa662c'
ROOT_FILES = (
    'website/integrated_app_platform_v363.py',
    'website/platform_shanlin_booking_source_v363.py',
    'website/platform_shanlin_booking_routes_v363.py',
    'shanlin_v363_staging/shanlin_v363_readonly.py',
    'tests/test_platform_booking_v363.py',
    'scripts/install_platform_v363.py',
)
PREREQUISITES = (
    'website/integrated_app_platform_v362.py',
    'website/platform_shanlin_booking_source_v362.py',
    'website/platform_console.py',
    'website/pilot_backend.py',
    'tests/test_platform_booking_v362.py',
)
BOOTSTRAP = ("from shanlin_v363_readonly import check_staging_configuration "
             "as _v363_check_before_existing_app_import\n"
             "_v363_check_before_existing_app_import()\n\n")
HOOK = ("\n\n# DOUBTS v3.6.3: attached ONLY to this pinned, isolated test copy.\n"
        "from shanlin_v363_readonly import attach_staging_router as _attach_v363\n"
        "_attach_v363(app, db)\n")


def _payloads(root: Path, shanlin_source: Path) -> tuple[dict[str,bytes],list[str]]:
    errors = []
    try:
        source = (shanlin_source/'main.py')
        if not source.is_file() or source.is_symlink():
            raise ValueError('pinned Shanlin main.py not found or is a symlink')
        raw = source.read_bytes()
        if hashlib.sha256(raw).hexdigest() != KNOWN_SHANLIN_V352_SHA256:
            raise ValueError('Shanlin source differs from reviewed v3.5.2; refuses patching unknown version')
        reminder = shanlin_source/'reminder_secure_v35.py'
        if not reminder.is_file() or reminder.is_symlink():
            raise ValueError('pinned Shanlin reminder_secure_v35.py dependency is missing')
        reminder_bytes = reminder.read_bytes()
        if hashlib.sha256(reminder_bytes).hexdigest() != KNOWN_REMINDER_V352_SHA256:
            raise ValueError('Shanlin reminder dependency differs from reviewed v3.5.2')
        text = raw.decode('utf-8')
        tree = ast.parse(text)
        literals = [n for n in ast.walk(tree) if isinstance(n,ast.Constant) and isinstance(n.value,str)]
        all_strings = '\n'.join(x.value for x in literals)
        if not all(k in all_strings for k in ('appointments','self_pay_booking','/api/admin/appointments')):
            raise ValueError('Shanlin original read-side contract not found')
    except (OSError,UnicodeError,SyntaxError,ValueError) as e:
        errors.append(str(e))
        return {}, errors
    payloads = {}
    for rel in ROOT_FILES:
        path=PACKAGE/rel
        if not path.is_file() or path.is_symlink():
            errors.append('Package missing: '+rel)
        else:
            payloads[rel] = path.read_bytes()
    payloads['shanlin_v363_staging/main.py'] = (BOOTSTRAP + text + HOOK).encode('utf-8')
    payloads['shanlin_v363_staging/reminder_secure_v35.py'] = reminder_bytes
    try: ast.parse(payloads['shanlin_v363_staging/main.py'])
    except (SyntaxError,TypeError): errors.append('Generated staging main.py is invalid')
    return payloads, errors


def inspect(root: Path, shanlin_source: Path):
    payloads,errors = _payloads(root,shanlin_source)
    for rel in PREREQUISITES:
        path=root/rel
        if not path.is_file() or path.is_symlink():
            errors.append('Missing v3.6.2 prerequisite: '+rel)
    actions=[]
    for rel,data in payloads.items():
        dst=root/rel
        if dst.is_symlink() or (dst.exists() and (not dst.is_file() or dst.read_bytes()!=data)):
            errors.append('Refuses to overwrite existing file: '+rel)
        elif dst.exists():
            actions.append('Already identical: '+rel)
        else:
            actions.append('Would add: '+rel)
    return payloads, errors, actions


def apply(root: Path,shanlin_source: Path):
    payloads,errors,actions=inspect(root,shanlin_source)
    if errors: return errors,actions
    created=[]
    try:
        for rel, data in payloads.items():
            dst=root/rel
            if dst.exists():continue
            dst.parent.mkdir(parents=True,exist_ok=True)
            fd=os.open(dst,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o644)
            created.append(dst)
            with os.fdopen(fd,'wb') as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
    except OSError:
        for dst in reversed(created):
            try: dst.unlink()
            except OSError: pass
        return ['Installation failed; newly created files rolled back'],actions
    return [],actions


def main():
    parser=argparse.ArgumentParser(description='Create a pinned, isolated Shanlin app stage; no production changes')
    parser.add_argument('--root',required=True)
    parser.add_argument('--shanlin-source',default=str(Path.home()/'Downloads'/'DOUBTS_v3.5.2_SHANLIN_STAGING'))
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    root=Path(args.root).expanduser().resolve()
    source=Path(args.shanlin_source).expanduser().resolve()
    if not root.is_dir() or not source.is_dir() or root==source:
        print('STOP: expected separate existing project and pinned Shanlin source directories')
        return 2
    errors,actions=apply(root,source) if args.apply else inspect(root,source)[1:]
    for msg in actions:print(msg)
    for err in errors:print('STOP:',err)
    if errors:return 2
    print('PASS: added test-only files and a pinned Shanlin main.py copy; originals unchanged'
          if args.apply else 'PASS: preflight only; original Shanlin main.py hash matches v3.5.2')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
