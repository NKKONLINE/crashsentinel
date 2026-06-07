import json
from database import Session, CrashReport, SyslogEntry, PredictionAlert
from analyzer import generate_prediction_alert
from datetime import datetime

def get_known_crash_symptoms() -> list:
    """Pull all extracted symptom patterns from past crashes."""
    session = Session()
    crashes = session.query(CrashReport).all()
    symptom_map = []
    for crash in crashes:
        if crash.symptoms:
            try:
                symptoms = json.loads(crash.symptoms)
                symptom_map.append({
                    "crash_id": crash.id,
                    "crash_type": crash.crash_type,
                    "root_cause": crash.root_cause,
                    "symptoms": symptoms
                })
            except:
                pass
    session.close()
    return symptom_map

def check_current_logs_for_precursors():
    """Compare live warning logs against known crash precursors."""
    session = Session()

    # Get recent warning logs (last 50)
    recent_warnings = session.query(SyslogEntry)\
        .filter(SyslogEntry.is_crash_precursor == 1)\
        .order_by(SyslogEntry.id.desc())\
        .limit(50).all()

    known_symptoms = get_known_crash_symptoms()
    alerts_generated = []

    for warning in recent_warnings:
        for known in known_symptoms:
            for symptom in known["symptoms"]:
                # Check for keyword overlap
                symptom_words = [w for w in symptom.lower().split() if len(w) > 4]
                if any(word in warning.message.lower() for word in symptom_words):

                    # Ask Gemma to evaluate the match
                    prediction = generate_prediction_alert(warning.message, known)

                    if prediction["confidence"] > 0.5:
                        alert = PredictionAlert(
                            timestamp=datetime.utcnow(),
                            matched_symptom=warning.message,
                            related_crash_id=known["crash_id"],
                            prediction_message=prediction["warning_message"],
                            confidence=prediction["confidence"]
                        )
                        session.add(alert)
                        alerts_generated.append(prediction)
                    break

    session.commit()
    session.close()
    return alerts_generated

def store_crash_report(crash_log: str, analysis: dict):
    """Store a crash report with AI analysis into the database."""
    session = Session()
    from database import CrashReport
    report = CrashReport(
        timestamp=datetime.utcnow(),
        crash_type=analysis.get("crash_type", "Unknown"),
        raw_log=crash_log,
        ai_explanation=analysis.get("explanation", ""),
        root_cause=analysis.get("root_cause", ""),
        severity=analysis.get("severity", "medium"),
        symptoms=json.dumps(analysis.get("symptoms", []))
    )
    session.add(report)
    session.commit()
    session.close()
    print(f"[predictor] Stored crash report: {analysis.get('crash_type')}")
    return report

if __name__ == "__main__":
    print("Testing predictor...")

    # First store a sample crash so predictor has history to work with
    from analyzer import analyze_crash
    test_log = "kernel: Out of memory: Killed process 1234 (chrome) total-vm:4096000kB"
    print("Storing sample crash into DB...")
    analysis = analyze_crash(test_log)
    store_crash_report(test_log, analysis)

    # Now run the precursor check
    print("\nChecking current logs for precursors...")
    alerts = check_current_logs_for_precursors()

    if alerts:
        print(f"\n  {len(alerts)} predictive alert(s) generated:")
        for a in alerts:
            print(f"  - {a['warning_message']}")
            print(f"    Confidence: {a['confidence']*100:.0f}%")
            print(f"    Action: {a['action_required']}")
    else:
        print("No alerts generated (no matching precursors found yet).")