"""Unified DOUBTS 8006 local platform: clinics + staff booking + engineering.

This is the same tested app used on port 8019, not a second admin backend.
The Shanlin transactional adapter still talks ONLY to the isolated localhost
8018 test service. Run via scripts/run_doubts_8006.py (preflight required).
Never deploy this preview to Railway or expose it beyond loopback.
"""
from integrated_app_platform_patient_stage import app
