"""Read the isolated exhibition timetable. Never write Firebase data."""
from copy import deepcopy
from datetime import date
import os
import re

from fastapi import HTTPException

TEST_URL = 'https://doubts-shanlin-test-default-rtdb.asia-southeast1.firebasedatabase.app'


def apply_exhibition_schedule(clinic):
    if os.getenv('PILOT_SHANLIN_STORAGE', '').strip() != 'firebase':
        return clinic
    try:
        # Reuse the dedicated named pilot app, not main.py's default app.
        if os.getenv('PILOT_SHANLIN_FIREBASE_URL', '').strip().rstrip('/') != TEST_URL:
            raise ValueError('Unexpected exhibition database')
        from pilot_backend import FirebaseStore
        from firebase_admin import db
        app = FirebaseStore()._app('shanlin')
        if app.project_id != 'doubts-shanlin-test':
            raise ValueError('Unexpected exhibition project')
        schedule = db.reference('booking_config/clinic', app=app).get()
        if not isinstance(schedule, dict) or schedule.get('clinicId') != 'shanlin' or schedule.get('name') != '山林診所' or schedule.get('integrationV363TestOnly') is not True:
            raise ValueError('Unverified exhibition clinic')
        days, hours, caps = (schedule.get(k) for k in
                             ('elderlyDates', 'elderlyTimes', 'capacityBySlot'))
        if not isinstance(days, list) or not 0 < len(days) <= 100 or len(set(days)) != len(days):
            raise ValueError('Invalid dates')
        for day in days:
            if not isinstance(day, str) or date.fromisoformat(day).isoformat() != day:
                raise ValueError('Invalid date')
        if not isinstance(hours, list) or not 0 < len(hours) <= 30 or len(set(hours)) != len(hours):
            raise ValueError('Invalid hours')
        if any(not isinstance(h, str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', h) for h in hours):
            raise ValueError('Invalid hour')
        if not isinstance(caps, dict) or set(caps) != set(days):
            raise ValueError('Invalid capacities')
        for day in days:
            slots = caps[day]
            if not isinstance(slots, dict) or not slots or any(h not in hours or type(n) is not int or not 1 <= n <= 100 for h, n in slots.items()):
                raise ValueError('Invalid slot capacity')
        result = deepcopy(clinic)
        result.update(elderlyDates=days, elderlyTimes=hours, capacityBySlot=caps)
        return result
    except Exception as exc:
        # Do not display credentials or silently fall back to expired dates.
        raise HTTPException(503, '展示排班暫時無法讀取，請稍後再試') from exc
