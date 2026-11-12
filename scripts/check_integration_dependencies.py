"""Non-mutating preflight, run at the ORIGINAL project root.

    python3 scripts/check_integration_dependencies.py
"""
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
checks = {
    "Original booking backend": root / "website/main.py",
    "Booking name database": root / "website/database.json",
    "Booking catalog JSON": root / "website/\u81ea\u8cbb\u9805\u76ee\u5c0d\u8a71\u8cc7\u6599\u5eab.json",
    "Pilot catalog parser": root / "website/pilot_shanlin_catalog.py",
    "Original admin page": root / "admin.html",
    "Booking page": root / "website/appointment2.html",
    "Public site CSS": root / "website/assets/css/main.css",
    "Homepage CSS": root / "website/assets/css/index.css",
    "Booking CSS": root / "website/assets/css/appointment2.css",
    "Homepage self-pay browser": root / "website/self_pay_chat.js",
    "Booking self-pay panel": root / "website/selfpay_panel.js",
    "Elderly voice UI": root / "website/yidian_elderly_voice.js",
    "Booking question UI": root / "website/booking_questions.js",
    "Logo": root / "website/assets/img/branding/logo.png",
    "Original admin CSS": root / "css/admin.css",
    "Taiwanese ASR browser": root / "website/yidian_taigi_stt.js",
    "Voice style": root / "website/yidian_speech.css",
    "Taiwanese ASR style": root / "website/yidian_taigi_stt.css",
    "Integrated entrypoint": root / "website/integrated_app.py",
    "Integrated asset router": root / "website/integrated_site.py",
}
missing = []
for label, path in checks.items():
    ok = path.is_file()
    print(("OK     " if ok else "MISSING") + " " + label + ": " + str(path.relative_to(root)))
    if not ok: missing.append(label)
if not (root / "website/clinic.js").is_file() and not (root / "clinic.js").is_file():
    missing.append("Clinic JS")
    print("MISSING Clinic JS: website/clinic.js or clinic.js")
else:
    print("OK      Clinic JS found")
print("\nRESULT: " + ("Missing dependencies; fix before starting" if missing else "All known critical files found"))
sys.exit(1 if missing else 0)
