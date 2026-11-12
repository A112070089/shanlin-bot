# Yidian DOUBTS - Phase 1 local integration overlay

Status: Local-preview patch, **not** a production-ready Railway release.

## What this patch does

- Registers the existing booking API (`website/main.py`), self-pay API, and Taigi routers in one FastAPI process.
- Adds the existing `/pilot` frontend and `/api/pilot/*` backend to that same process without changing the Firebase transaction code or staff revision checks.
- Serves `/`, `/index.html`, `/appointment2.html`, `/admin.html` and known public CSS/JS/image assets at a single local origin, e.g. `http://127.0.0.1:8006`.
- Generates `site-config.js` at request time so the booking frontend uses the same origin (8006 rather than hardcoded 8000); preserves the separately deployed original appointment-admin API.
- Adjusts the old 8005 and external admin links to the local `/pilot` and `/admin.html` navigation **in the HTTP response only**, leaving the original HTML/JS untouched on disk.
- Blocks the old unsafe `GET /api/firebase/test-write` endpoint, which writes a database record on a GET request.
- Uses a distinct pilot-session cookie name to avoid collisions between the original 8005 test server and this integrated preview.

## What is NOT yet merged

1. The original appointment administrator backend is a **different service** (historical 8001 / `shanlin-bot-production`), and its source was not in the 17-file archive. `/admin.html` is hosted here, but it still calls the original admin API, so login requires that API, compatible CORS settings, and verified clinic/database ownership. The original site's clinic label alone is NOT evidence of database ownership. Do not work with real patient appointments until verified.
2. The 8005 pilot catalog draft and the original self-pay catalog/booking API remain separate, with no writeback or automatic synchronization. The current pilot version-control protection remains unchanged.
3. Taigi audio relies on separate local services at 8002 (TTS), 8003 (STT), and 8004 (text translation), using macOS MLX models and speech-draft material requiring clinical/native-language review. They are NOT automatically portable to Railway, and the existing research model licenses prohibit unapproved commercial use.
4. The public pilot and old appointment backend have distinct authentication and tenant models; combining their URL entrypoint does not mean a shared login or authorized data exchange.
5. The supplied ZIP omitted critical data/assets/modules (`database.json`, self-pay catalog JSON, `pilot_shanlin_catalog.py`, several JS/CSS/images). This overlay must be placed in the **original complete Mac project**, not run using only the uploaded 17 files.

## Installation (adds files; leaves originals untouched)

In Finder, back up the original folder first. Copy the overlay's `website/`, `scripts/`, and `tests/` files into the existing project ROOT. Use `unzip -n` to prevent overwriting any existing same-name files. If you previously installed this overlay and need a newer version, inspect the changes before replacing anything.

```bash
cd "/path/to/original-project-root"
unzip -n "$HOME/Downloads/yidian_phase1_integration_patch.zip" -d .

python3 scripts/check_integration_dependencies.py
cd website
python3 -m uvicorn integrated_app:app --host 127.0.0.1 --port 8006
```

Open on the Mac (the old 5500 and 8005 pages are not part of this new entrypoint):

- `http://127.0.0.1:8006/` - original home page
- `http://127.0.0.1:8006/appointment2.html?p=SELF_PAY&directSelfPay=1` - original self-pay appointment with voice switches
- `http://127.0.0.1:8006/admin.html` - original appointment-admin page (calls separate 8001 API)
- `http://127.0.0.1:8006/pilot?clinic=shanlin&view=admin` - original pilot admin (requires separately authorized login)
- `http://127.0.0.1:8006/integrated/health` - non-sensitive integration status

Run read-only route tests from the project ROOT:

```bash
python3 -m pytest -q tests/test_integrated_routes.py
```

These tests make only local HTTP TestClient requests. They do not place bookings, upload catalogs, publish prices, or write to Firebase. The tests do not replace actual UI/STT/TTS/browser, legacy-login and data-source verification. Don't use real patient records as test input.

If `8006` is occupied, choose another unused port. Taigi 8002/8003/8004 must still be started separately using their existing approved local demo instructions.

## Security and deployment blockers

- Never upload `.env`, Firebase service-account JSON, clinic records, patient records, `.venv`, model weights, or backups to the code repository.
- The pilot's local demo user store/session memory and the original 8001 admin service are not production-integrated identity infrastructure.
- Confirm whether the website represents Yidian or Shanlin before pointing it at real Firebase/admin systems; do not silently share patient data between these clinics.
- Review existing wildcard CORS, admin password stored in browser sessionStorage, patient-data logs/error messages, local disk persistence, rate limits, access control, HTTPS proxy handling, and database ownership before public deployment.
- Commercial licensing and professional review are prerequisites for Taigi model deployment. Use the original local fallback until that is resolved.
- Before Railway release, acquire and inspect the original administrative backend source and complete deployment configuration. Decide whether to keep that backend separate behind a verified URL or migrate it with an explicit compatibility and auth plan. Test with isolated synthetic records first.
