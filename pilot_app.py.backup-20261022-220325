"""Standalone demo: cd website && python -m uvicorn pilot_app:app --port 8005 --reload"""
from fastapi import FastAPI
from pilot_backend import router

app = FastAPI(title='頤典雙診所公版試行', version='3.0.0')
app.include_router(router)
