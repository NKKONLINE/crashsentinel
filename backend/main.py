import json
import threading
import time
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import Session, CrashReport, PredictionAlert
from log_collector import parse_and_store_logs
from analyzer import analyze_crash, summarize_crash_history
from predictor import check_current_logs_for_precursors, store_crash_report
from datetime import datetime

app = FastAPI(title="CrashSentinel API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

# ── Background monitoring loop ──────────────────────────────────────
def monitoring_loop():
    print("[Monitor] Background monitoring started...")
    while True:
        try:
            print("[Monitor] Scanning logs...")
            crashes, warnings = parse_and_store_logs()

            # Analyze each crash found and store it
            session = Session()
            for crash_log in crashes:
                # Avoid duplicate entries
                existing = session.query(CrashReport)\
                    .filter(CrashReport.raw_log == crash_log).first()
                if not existing:
                    print(f"[Monitor] New crash found, analyzing with Gemma...")
                    analysis = analyze_crash(crash_log)
                    store_crash_report(crash_log, analysis)
            session.close()

            # Check for predictive alerts
            alerts = check_current_logs_for_precursors()
            if alerts:
                print(f"[Monitor]   {len(alerts)} new predictive alert(s) generated!")

        except Exception as e:
            print(f"[Monitor] Error in monitoring loop: {e}")

        time.sleep(60)  # scan every 60 seconds

# Start background thread on startup
monitor_thread = threading.Thread(target=monitoring_loop, daemon=True)
monitor_thread.start()

# ── API Routes ───────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "CrashSentinel is running", "message": "Visit /docs for API reference"}

@app.get("/reports")
def get_reports(limit: int = 20):
    session = Session()
    reports = session.query(CrashReport)\
        .order_by(CrashReport.timestamp.desc()).limit(limit).all()
    result = [{
        "id": r.id,
        "timestamp": r.timestamp.isoformat(),
        "crash_type": r.crash_type,
        "severity": r.severity,
        "root_cause": r.root_cause,
        "explanation": r.ai_explanation,
        "symptoms": json.loads(r.symptoms) if r.symptoms else [],
        "raw_log": r.raw_log
    } for r in reports]
    session.close()
    return result

@app.get("/alerts")
def get_alerts():
    session = Session()
    alerts = session.query(PredictionAlert)\
        .filter(PredictionAlert.is_dismissed == 0)\
        .order_by(PredictionAlert.timestamp.desc()).all()
    result = [{
        "id": a.id,
        "timestamp": a.timestamp.isoformat(),
        "message": a.prediction_message,
        "confidence": a.confidence,
        "matched_symptom": a.matched_symptom
    } for a in alerts]
    session.close()
    return result

@app.post("/alerts/{alert_id}/dismiss")
def dismiss_alert(alert_id: int):
    session = Session()
    alert = session.query(PredictionAlert).get(alert_id)
    if alert:
        alert.is_dismissed = 1
        session.commit()
    session.close()
    return {"status": "dismissed"}

@app.get("/summary")
def get_summary():
    session = Session()
    reports = session.query(CrashReport).all()
    history = [{
        "crash_type": r.crash_type,
        "root_cause": r.root_cause,
        "severity": r.severity
    } for r in reports]
    session.close()
    summary = summarize_crash_history(history)
    return {"summary": summary}

@app.post("/analyze")
def analyze_manual(payload: dict):
    """Manually submit a log for analysis."""
    log_text = payload.get("log", "")
    if not log_text:
        return {"error": "No log text provided"}
    result = analyze_crash(log_text)
    # Auto store it
    store_crash_report(log_text, result)
    return result

@app.get("/stats")
def get_stats():
    """Quick stats overview for the dashboard."""
    session = Session()
    total_crashes = session.query(CrashReport).count()
    critical = session.query(CrashReport)\
        .filter(CrashReport.severity == "critical").count()
    high = session.query(CrashReport)\
        .filter(CrashReport.severity == "high").count()
    active_alerts = session.query(PredictionAlert)\
        .filter(PredictionAlert.is_dismissed == 0).count()
    session.close()
    return {
        "total_crashes": total_crashes,
        "critical": critical,
        "high": high,
        "active_alerts": active_alerts
    }
@app.get("/stats")
def get_stats():
    session = Session()
    total_crashes = session.query(CrashReport).count()
    critical = session.query(CrashReport)\
        .filter(CrashReport.severity == "critical").count()
    high = session.query(CrashReport)\
        .filter(CrashReport.severity == "high").count()
    active_alerts = session.query(PredictionAlert)\
        .filter(PredictionAlert.is_dismissed == 0).count()
    session.close()
    return {
        "total_crashes": total_crashes,
        "critical": critical,
        "high": high,
        "active_alerts": active_alerts
    }

# ← ADD THE NEW ROUTE RIGHT HERE ↓

@app.get("/charts")
def get_chart_data():
    session = Session()
    reports = session.query(CrashReport).order_by(CrashReport.timestamp).all()
    
    from collections import defaultdict
    daily = defaultdict(int)
    severity_counts = defaultdict(int)
    type_counts = defaultdict(int)

    for r in reports:
        day = r.timestamp.strftime("%Y-%m-%d")
        daily[day] += 1
        severity_counts[r.severity] += 1
        type_counts[r.crash_type] += 1

    session.close()
    return {
        "daily": [{"date": k, "crashes": v} for k, v in sorted(daily.items())],
        "severity": [{"name": k, "value": v} for k, v in severity_counts.items()],
        "types": [{"name": k, "value": v} for k, v in type_counts.items()]
    }