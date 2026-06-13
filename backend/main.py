"""
main.py — CrashSentinel API
FastAPI application with background log monitoring.

Routes:
  GET  /             — health check
  GET  /reports      — list crash reports (default last 20)
  GET  /alerts       — list active (undismissed) prediction alerts
  POST /alerts/{id}/dismiss  — dismiss a prediction alert
  GET  /summary      — AI-generated health summary
  GET  /stats        — dashboard stat counts
  GET  /charts       — chart data (daily, severity, type breakdowns)
  POST /analyze      — manually submit a log for immediate analysis
"""

import json
import logging
import threading
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from database import Session, CrashReport, PredictionAlert
from log_collector import parse_and_store_logs
from analyzer import analyze_crash, summarize_crash_history
from predictor import check_current_logs_for_precursors, store_crash_report

# ── Logging ───────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("main")

# ── Lifespan (replaces deprecated @app.on_event) ─────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    start_monitor()   # runs on startup
    yield             # app is now running
                      # anything after yield runs on shutdown

# ── App ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="CrashSentinel API",
    description="Local AI crash detection and prediction system",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Background monitoring ─────────────────────────────────────────────

def monitoring_loop():
    logger.info("[Monitor] Background monitoring started (60 s interval)")
    while True:
        try:
            logger.info("[Monitor] Scanning logs...")
            crashes, warnings = parse_and_store_logs()

            if crashes:
                session = Session()
                try:
                    for crash_log in crashes:
                        existing = (
                            session.query(CrashReport)
                            .filter(CrashReport.raw_log == crash_log)
                            .first()
                        )
                        if not existing:
                            logger.info("[Monitor] New crash found — analysing with Gemma...")
                            analysis = analyze_crash(crash_log)
                            store_crash_report(crash_log, analysis)
                finally:
                    session.close()

            alerts = check_current_logs_for_precursors()
            if alerts:
                logger.info(f"[Monitor] {len(alerts)} new predictive alert(s) generated")

        except Exception as e:
            logger.error(f"[Monitor] Unhandled error in monitoring loop: {e}", exc_info=True)

        time.sleep(60)


def start_monitor():
    """Start the background monitor thread. Called once on app startup."""
    t = threading.Thread(target=monitoring_loop, daemon=True, name="monitor")
    t.start()
    logger.info("[Monitor] Thread started")


# ── Routes ────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "CrashSentinel is running", "docs": "/docs"}


@app.get("/reports")
def get_reports(limit: int = 20):
    """Return the most recent crash reports, newest first."""
    session = Session()
    try:
        reports = (
            session.query(CrashReport)
            .order_by(CrashReport.timestamp.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id":              r.id,
                "timestamp":       r.timestamp.isoformat(),
                "crash_type":      r.crash_type,
                "severity":        r.severity,
                "root_cause":      r.root_cause,
                "explanation":     r.ai_explanation,
                "symptoms":        _parse_json_field(r.symptoms),
                "recommendations": _parse_json_field(r.recommendations),
                "raw_log":         r.raw_log,
                "source_os":       r.source_os,
                "is_simulated":    bool(r.is_simulated),
            }
            for r in reports
        ]
    finally:
        session.close()


@app.get("/alerts")
def get_alerts():
    """Return all active (undismissed) prediction alerts, newest first."""
    session = Session()
    try:
        alerts = (
            session.query(PredictionAlert)
            .filter(PredictionAlert.is_dismissed == 0)
            .order_by(PredictionAlert.timestamp.desc())
            .all()
        )
        return [
            {
                "id":              a.id,
                "timestamp":       a.timestamp.isoformat(),
                "message":         a.prediction_message,
                "confidence":      round(a.confidence, 4),
                "matched_symptom": a.matched_symptom,
                "crash_id":        a.related_crash_id,
            }
            for a in alerts
        ]
    finally:
        session.close()


@app.post("/alerts/{alert_id}/dismiss")
def dismiss_alert(alert_id: int):
    """Mark a prediction alert as dismissed."""
    session = Session()
    try:
        alert = session.get(PredictionAlert, alert_id)
        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")
        alert.is_dismissed = 1
        session.commit()
        return {"status": "dismissed", "id": alert_id}
    finally:
        session.close()


@app.get("/summary")
def get_summary():
    """Ask Gemma to summarise the crash history."""
    session = Session()
    try:
        reports = session.query(CrashReport).all()
        history = [
            {
                "crash_type": r.crash_type,
                "root_cause": r.root_cause,
                "severity":   r.severity,
            }
            for r in reports
        ]
    finally:
        session.close()

    summary = summarize_crash_history(history)
    return {"summary": summary}


@app.get("/stats")
def get_stats():
    """Return stat counts for the dashboard."""
    session = Session()
    try:
        total_crashes  = session.query(CrashReport).count()
        critical       = session.query(CrashReport).filter(CrashReport.severity == "critical").count()
        high           = session.query(CrashReport).filter(CrashReport.severity == "high").count()
        active_alerts  = session.query(PredictionAlert).filter(PredictionAlert.is_dismissed == 0).count()
    finally:
        session.close()

    return {
        "total_crashes": total_crashes,
        "critical":      critical,
        "high":          high,
        "active_alerts": active_alerts,
    }


@app.get("/charts")
def get_chart_data():
    """Return aggregated data for frontend charts."""
    session = Session()
    try:
        reports = session.query(CrashReport).order_by(CrashReport.timestamp).all()
    finally:
        session.close()

    daily          = defaultdict(int)
    severity_counts = defaultdict(int)
    type_counts    = defaultdict(int)

    for r in reports:
        day = r.timestamp.strftime("%Y-%m-%d")
        daily[day] += 1
        severity_counts[r.severity or "unknown"] += 1
        type_counts[r.crash_type or "Unknown"] += 1

    return {
        "daily":    [{"date": k, "crashes": v} for k, v in sorted(daily.items())],
        "severity": [{"name": k, "value": v} for k, v in severity_counts.items()],
        "types":    [{"name": k, "value": v} for k, v in type_counts.items()],
    }


@app.post("/analyze")
def analyze_manual(payload: dict):
    """
    Manually submit a raw log string for immediate AI analysis.
    The result is stored and returned.
    """
    log_text = payload.get("log", "").strip()
    if not log_text:
        raise HTTPException(status_code=400, detail="No log text provided")

    result = analyze_crash(log_text)
    store_crash_report(log_text, result)
    return result


# ── Utility ───────────────────────────────────────────────────────────

def _parse_json_field(value) -> list:
    """Safely parse a JSON column that should be a list. Returns [] on failure."""
    if not value:
        return []
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []