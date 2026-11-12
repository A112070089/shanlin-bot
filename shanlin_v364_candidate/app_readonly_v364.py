"""Only entrypoint permitted for the pinned Shanlin candidate during offline integration.

Requires an explicitly independent TEST Firebase; all routes except the signed,
PII-free v3.6.3 summary are blocked. Never run main:app directly.
"""
from shanlin_v363_readonly import check_staging_configuration
check_staging_configuration()  # must occur BEFORE the source main.py imports Firebase

import importlib.util
import sys
from pathlib import Path

base = Path(__file__).resolve().parent
sys.path.insert(0, str(base))
spec = importlib.util.spec_from_file_location('_doubts_v364_pinned_shanlin_main', base / 'main.py')
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
app = module.app  # firewall and signed read route already attached by pinned main.py
