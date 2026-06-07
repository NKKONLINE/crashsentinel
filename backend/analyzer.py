import requests
import json

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "gemma3:4b"

def ask_gemma(prompt: str, system: str = "") -> str:
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "system": system,
        "stream": False
    }
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=120)
        return response.json().get("response", "")
    except requests.exceptions.ConnectionError:
        return "ERROR: Ollama is not running. Please run 'ollama serve' in a separate terminal."
    except Exception as e:
        return f"ERROR: {str(e)}"

def analyze_crash(raw_log: str) -> dict:
    system_prompt = """You are a systems reliability expert and crash analyst.
    Analyze crash logs and return ONLY a JSON object with these exact keys:
    - crash_type: string (e.g., "OOM Killer", "Kernel Panic", "Segfault")
    - severity: string (one of: "low", "medium", "high", "critical")
    - root_cause: string (concise technical cause)
    - explanation: string (plain English explanation for the user)
    - symptoms: list of strings (warning signs that appeared before this crash)
    - recommendations: list of strings (what to do to prevent recurrence)
    Return only valid JSON, no extra text, no markdown backticks."""

    prompt = f"Analyze this crash log:\n\n{raw_log}"
    response = ask_gemma(prompt, system_prompt)

    try:
        clean = response.strip().strip("```json").strip("```").strip()
        return json.loads(clean)
    except json.JSONDecodeError:
        return {
            "crash_type": "Unknown",
            "severity": "medium",
            "root_cause": "Could not parse AI response",
            "explanation": response,
            "symptoms": [],
            "recommendations": []
        }

def generate_prediction_alert(current_symptom: str, past_crash: dict) -> dict:
    system_prompt = """You are a predictive systems analyst.
    Given a current system warning and a past crash that had similar symptoms,
    estimate crash probability and warn the user.
    Return ONLY a JSON object with these exact keys:
    - confidence: float between 0 and 1
    - time_estimate: string (e.g., "within 10-30 minutes if load continues")
    - warning_message: string (clear, urgent but not alarmist user-facing message)
    - action_required: string (what the user should do RIGHT NOW)
    No extra text, no markdown backticks."""

    prompt = f"""Current system symptom: {current_symptom}

Past crash with similar symptoms:
- Type: {past_crash.get('crash_type')}
- Root cause: {past_crash.get('root_cause')}
- Symptoms that preceded it: {past_crash.get('symptoms')}

Should the user be alarmed? Predict outcome."""

    response = ask_gemma(prompt, system_prompt)
    try:
        clean = response.strip().strip("```json").strip("```").strip()
        return json.loads(clean)
    except:
        return {
            "confidence": 0.6,
            "time_estimate": "Unknown",
            "warning_message": response,
            "action_required": "Monitor system closely"
        }

def summarize_crash_history(crash_history: list) -> str:
    if not crash_history:
        return "No crash history available yet. The system will analyze patterns as crashes are detected."

    prompt = f"""Here is a history of system crashes:
{json.dumps(crash_history, indent=2)}

Provide a 3-5 sentence summary covering:
1. Most common crash patterns
2. Root causes that keep recurring
3. Overall system health assessment
4. Top 2 recommendations"""

    return ask_gemma(prompt)

if __name__ == "__main__":
    print("Testing Gemma 4 connection...")
    test_log = "kernel: Out of memory: Killed process 1234 (chrome) total-vm:4096000kB, anon-rss:3200000kB"
    print(f"\nAnalyzing test log:\n{test_log}\n")
    result = analyze_crash(test_log)
    print("Result:")
    print(json.dumps(result, indent=2))