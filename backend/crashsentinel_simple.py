"""
crashsentinel_simple.py
Minimal HTTP server using only Python stdlib — no uvicorn, no socket permission issues.
Run: python crashsentinel_simple.py
API will be at http://localhost:8001
"""

import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
from collections import defaultdict

# Import our app modules
from database import Session, CrashReport, PredictionAlert
from analyzer import analyze_crash, summarize_crash_history
from predictor import check_current_logs_for_precursors, store_crash_report
from log_collector import parse_and_store_logs
import threading
import time
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s — %(message)s")
logger = logging.getLogger("simple_server")

PORT = 8888

def parse_json_field(value):
    if not value:
        return []
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []

def monitoring_loop():
    logger.info("[Monitor] Background monitoring started (60s interval)")
    while True:
        try:
            crashes, warnings = parse_and_store_logs()
            if crashes:
                session = Session()
                try:
                    for crash_log in crashes:
                        existing = session.query(CrashReport).filter(CrashReport.raw_log == crash_log).first()
                        if not existing:
                            analysis = analyze_crash(crash_log)
                            store_crash_report(crash_log, analysis)
                finally:
                    session.close()
            check_current_logs_for_precursors()
        except Exception as e:
            logger.error(f"[Monitor] Error: {e}")
        time.sleep(60)

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # suppress default HTTP logs

    def send_json(self, code, data):
        body = json.dumps(data, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0]

        if path == "/":
            self.send_json(200, {"status": "CrashSentinel is running"})

        elif path == "/stats":
            session = Session()
            try:
                self.send_json(200, {
                    "total_crashes": session.query(CrashReport).count(),
                    "critical": session.query(CrashReport).filter(CrashReport.severity == "critical").count(),
                    "high": session.query(CrashReport).filter(CrashReport.severity == "high").count(),
                    "active_alerts": session.query(PredictionAlert).filter(PredictionAlert.is_dismissed == 0).count(),
                })
            finally:
                session.close()

        elif path == "/reports":
            session = Session()
            try:
                reports = session.query(CrashReport).order_by(CrashReport.timestamp.desc()).limit(20).all()
                self.send_json(200, [{
                    "id": r.id, "timestamp": r.timestamp.isoformat(),
                    "crash_type": r.crash_type, "severity": r.severity,
                    "root_cause": r.root_cause, "explanation": r.ai_explanation,
                    "symptoms": parse_json_field(r.symptoms),
                    "recommendations": parse_json_field(r.recommendations),
                    "raw_log": r.raw_log, "source_os": r.source_os,
                    "is_simulated": bool(r.is_simulated),
                } for r in reports])
            finally:
                session.close()

        elif path == "/alerts":
            session = Session()
            try:
                alerts = session.query(PredictionAlert).filter(PredictionAlert.is_dismissed == 0).order_by(PredictionAlert.timestamp.desc()).all()
                self.send_json(200, [{
                    "id": a.id, "timestamp": a.timestamp.isoformat(),
                    "message": a.prediction_message, "confidence": round(a.confidence, 4),
                    "matched_symptom": a.matched_symptom, "crash_id": a.related_crash_id,
                } for a in alerts])
            finally:
                session.close()

        elif path == "/charts":
            session = Session()
            try:
                reports = session.query(CrashReport).order_by(CrashReport.timestamp).all()
            finally:
                session.close()
            daily, sev, types = defaultdict(int), defaultdict(int), defaultdict(int)
            for r in reports:
                daily[r.timestamp.strftime("%Y-%m-%d")] += 1
                sev[r.severity or "unknown"] += 1
                types[r.crash_type or "Unknown"] += 1
            self.send_json(200, {
                "daily":    [{"date": k, "crashes": v} for k, v in sorted(daily.items())],
                "severity": [{"name": k, "value": v} for k, v in sev.items()],
                "types":    [{"name": k, "value": v} for k, v in types.items()],
            })

        elif path == "/summary":
            session = Session()
            try:
                reports = session.query(CrashReport).all()
                history = [{"crash_type": r.crash_type, "root_cause": r.root_cause, "severity": r.severity} for r in reports]
            finally:
                session.close()
            self.send_json(200, {"summary": summarize_crash_history(history)})

        else:
            self.send_json(404, {"detail": "Not found"})

    def do_POST(self):
        path = self.path.split("?")[0]
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}

        if path == "/analyze":
            log_text = body.get("log", "").strip()
            if not log_text:
                self.send_json(400, {"detail": "No log text provided"})
                return
            result = analyze_crash(log_text)
            store_crash_report(log_text, result)
            self.send_json(200, result)

        elif path.startswith("/alerts/") and path.endswith("/dismiss"):
            try:
                alert_id = int(path.split("/")[2])
            except (ValueError, IndexError):
                self.send_json(400, {"detail": "Invalid alert ID"})
                return
            session = Session()
            try:
                alert = session.get(PredictionAlert, alert_id)
                if not alert:
                    self.send_json(404, {"detail": "Alert not found"})
                    return
                alert.is_dismissed = 1
                session.commit()
                self.send_json(200, {"status": "dismissed", "id": alert_id})
            finally:
                session.close()

        else:
            self.send_json(404, {"detail": "Not found"})


if __name__ == "__main__":
    # Start background monitor
    t = threading.Thread(target=monitoring_loop, daemon=True)
    t.start()

    server = HTTPServer(("127.0.0.1", PORT), Handler)
    logger.info(f"CrashSentinel running on http://localhost:{PORT}")
    logger.info("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down.")
        server.server_close()