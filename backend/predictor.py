"""
predictor.py — CrashSentinel
Compares live syslog warnings against known crash symptom patterns.
Generates PredictionAlerts when a match is found and Gemma confidence > 0.5.
"""

import json
import logging
import platform
from datetime import datetime

from database import Session, CrashReport, SyslogEntry, PredictionAlert
from analyzer import generate_prediction_alert

logger = logging.getLogger("predictor")


# ── Symptom knowledge base ────────────────────────────────────────────

def get_known_crash_symptoms() -> list:
    """
    Pull all symptom patterns extracted from past crash reports.
    Returns a list of dicts: {crash_id, crash_type, root_cause, symptoms}.
    """
    session = Session()
    try:
        crashes = session.query(CrashReport).all()
        symptom_map = []
        for crash in crashes:
            if not crash.symptoms:
                continue
            try:
                symptoms = json.loads(crash.symptoms)
                if symptoms:
                    symptom_map.append({
                        "crash_id":   crash.id,
                        "crash_type": crash.crash_type,
                        "root_cause": crash.root_cause,
                        "symptoms":   symptoms,
                    })
            except json.JSONDecodeError:
                logger.warning(f"[predictor] Could not parse symptoms for crash id={crash.id}")
        return symptom_map
    finally:
        session.close()


# ── Precursor check ───────────────────────────────────────────────────

def check_current_logs_for_precursors() -> list:
    """
    Compare the 50 most recent warning log entries against known crash precursors.
    For each match with confidence > 0.5, stores a PredictionAlert (deduped).
    Returns a list of prediction dicts for the caller to log/report.
    """
    session = Session()
    alerts_generated = []

    try:
        recent_warnings = (
            session.query(SyslogEntry)
            .filter(SyslogEntry.is_crash_precursor == 1)
            .order_by(SyslogEntry.id.desc())
            .limit(50)
            .all()
        )

        known_symptoms = get_known_crash_symptoms()

        for warning in recent_warnings:
            matched = False
            for known in known_symptoms:
                if matched:
                    break
                for symptom in known["symptoms"]:
                    # Keyword overlap: only meaningful words (len > 4)
                    symptom_words = [w for w in symptom.lower().split() if len(w) > 4]
                    if not symptom_words:
                        continue

                    if not any(word in warning.message.lower() for word in symptom_words):
                        continue

                    # ── Dedup: don't re-alert on the same warning + crash pair ──
                    already_alerted = (
                        session.query(PredictionAlert)
                        .filter(
                            PredictionAlert.matched_symptom == warning.message,
                            PredictionAlert.related_crash_id == known["crash_id"],
                        )
                        .first()
                    )
                    if already_alerted:
                        matched = True
                        break

                    # Ask Gemma to evaluate the match
                    prediction = generate_prediction_alert(warning.message, known)
                    confidence = prediction.get("confidence", 0.0)

                    if confidence > 0.5:
                        alert = PredictionAlert(
                            timestamp=datetime.utcnow(),
                            matched_symptom=warning.message,
                            related_crash_id=known["crash_id"],
                            prediction_message=prediction.get("warning_message", ""),
                            confidence=confidence,
                            is_simulated=warning.is_simulated,
                        )
                        session.add(alert)
                        alerts_generated.append(prediction)
                        logger.info(
                            f"[predictor] Alert generated: {prediction.get('warning_message', '')[:80]} "
                            f"(confidence={confidence:.0%})"
                        )

                    matched = True
                    break  # one alert per warning is enough

        session.commit()

    except Exception as e:
        logger.error(f"[predictor] Error in precursor check: {e}")
        session.rollback()
    finally:
        session.close()

    return alerts_generated


# ── Crash report storage ──────────────────────────────────────────────

def store_crash_report(crash_log: str, analysis: dict, is_simulated: int = 0) -> CrashReport:
    """
    Persist a crash report + its AI analysis to the database.
    Returns the saved CrashReport instance.
    """
    session = Session()
    try:
        report = CrashReport(
            timestamp=datetime.utcnow(),
            crash_type=analysis.get("crash_type", "Unknown"),
            raw_log=crash_log,
            ai_explanation=analysis.get("explanation", ""),
            root_cause=analysis.get("root_cause", ""),
            severity=analysis.get("severity", "medium"),
            symptoms=json.dumps(analysis.get("symptoms", [])),
            recommendations=json.dumps(analysis.get("recommendations", [])),
            source_os=platform.system().lower(),
            is_simulated=is_simulated,
        )
        session.add(report)
        session.commit()
        session.refresh(report)
        logger.info(f"[predictor] Stored crash report: {report.crash_type} (id={report.id})")
        return report
    except Exception as e:
        logger.error(f"[predictor] Failed to store crash report: {e}")
        session.rollback()
        raise
    finally:
        session.close()


# ── Dev runner ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO)

    from analyzer import analyze_crash

    print("Testing predictor...\n")
    test_log = "kernel: Out of memory: Killed process 1234 (chrome) total-vm:4096000kB"
    print(f"Storing sample crash: {test_log}")
    analysis = analyze_crash(test_log)
    store_crash_report(test_log, analysis)

    print("\nChecking current logs for precursors...")
    alerts = check_current_logs_for_precursors()

    if alerts:
        print(f"\n{len(alerts)} predictive alert(s) generated:")
        for a in alerts:
            print(f"  - {a.get('warning_message')}")
            print(f"    Confidence : {a.get('confidence', 0) * 100:.0f}%")
            print(f"    Action     : {a.get('action_required')}")
    else:
        print("No alerts generated (no matching precursors found yet).")