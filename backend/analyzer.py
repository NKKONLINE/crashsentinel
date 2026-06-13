"""
analyzer.py — CrashSentinel
Gemma3 integration via Ollama.
Handles crash analysis, predictive alert generation, and history summarisation.

Environment variables:
  OLLAMA_URL   — default http://localhost:11434/api/generate
  OLLAMA_MODEL — default gemma3:4b
"""

import os
import re
import json
import logging
import requests

logger = logging.getLogger("analyzer")

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")
MODEL      = os.environ.get("OLLAMA_MODEL", "gemma3:4b")

# ── Helpers ───────────────────────────────────────────────────────────

def _strip_json_fences(text: str) -> str:
    """
    Remove markdown code fences that Gemma sometimes wraps around JSON.
    Handles ```json ... ```, ``` ... ```, and leading/trailing whitespace.
    """
    text = text.strip()
    # Remove opening fence (```json or ```)
    text = re.sub(r"^```(?:json)?\s*", "", text)
    # Remove closing fence
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def ask_gemma(prompt: str, system: str = "", retries: int = 2) -> str:
    """
    Send a prompt to Gemma via Ollama.
    Retries up to `retries` times on timeout.
    Returns the response string, or an ERROR: prefixed message on failure.
    """
    payload = {
        "model":  MODEL,
        "prompt": prompt,
        "system": system,
        "stream": False,
    }
    for attempt in range(1, retries + 2):
        try:
            response = requests.post(OLLAMA_URL, json=payload, timeout=120)
            response.raise_for_status()
            return response.json().get("response", "")
        except requests.exceptions.ConnectionError:
            return "ERROR: Ollama is not running. Start it with: ollama serve"
        except requests.exceptions.Timeout:
            if attempt <= retries:
                logger.warning(f"[analyzer] Ollama timeout (attempt {attempt}/{retries + 1}), retrying...")
            else:
                return "ERROR: Ollama timed out after all retries."
        except requests.exceptions.HTTPError as e:
            return f"ERROR: Ollama HTTP error — {e}"
        except Exception as e:
            return f"ERROR: {e}"
    return "ERROR: Unknown failure in ask_gemma."


# ── Core analysis functions ───────────────────────────────────────────

def analyze_crash(raw_log: str) -> dict:
    """
    Analyse a raw crash log with Gemma and return a structured dict.
    Always returns a valid dict (never raises).
    """
    system_prompt = (
        "You are a senior systems reliability engineer and crash analyst. "
        "Analyse the crash log the user provides and return ONLY a JSON object "
        "with these exact keys — no extra text, no markdown backticks:\n"
        "{\n"
        '  "crash_type":       string  — short label, e.g. "OOM Killer", "Kernel Panic", "Segfault"\n'
        '  "severity":         string  — exactly one of: "low", "medium", "high", "critical"\n'
        '  "root_cause":       string  — concise technical cause (1-2 sentences)\n'
        '  "explanation":      string  — plain-English explanation a non-expert can understand\n'
        '  "symptoms":         array of strings — observable warning signs that appear BEFORE this type of crash\n'
        '  "recommendations":  array of strings — concrete steps to prevent recurrence\n'
        "}\n"
        "If the log is ambiguous, still return valid JSON with your best assessment. "
        "Never return null for any field."
    )

    prompt = f"Analyse this crash log and return only JSON:\n\n{raw_log}"
    response = ask_gemma(prompt, system_prompt)

    if response.startswith("ERROR:"):
        logger.error(f"[analyzer] Gemma unavailable: {response}")
        return _fallback_analysis(raw_log, response)

    try:
        return json.loads(_strip_json_fences(response))
    except json.JSONDecodeError:
        logger.warning(f"[analyzer] JSON parse failed, attempting extraction. Raw: {response[:200]}")
        # Last-ditch: find the first {...} block in the response
        match = re.search(r"\{.*\}", response, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return _fallback_analysis(raw_log, response)


def _fallback_analysis(raw_log: str, raw_response: str) -> dict:
    return {
        "crash_type":      "Unknown",
        "severity":        "medium",
        "root_cause":      "AI analysis unavailable",
        "explanation":     raw_response,
        "symptoms":        [],
        "recommendations": ["Check Ollama is running: ollama serve"],
    }


def generate_prediction_alert(current_symptom: str, past_crash: dict) -> dict:
    """
    Given a live warning and a past crash with similar symptoms, ask Gemma
    to estimate crash probability and return a structured prediction dict.
    Always returns a valid dict (never raises).
    """
    system_prompt = (
        "You are a predictive systems analyst. "
        "Given a current system warning and a past crash that had similar symptoms, "
        "estimate crash probability and advise the user. "
        "Return ONLY a JSON object with these exact keys — no extra text, no markdown backticks:\n"
        "{\n"
        '  "confidence":       float between 0.0 and 1.0\n'
        '  "time_estimate":    string — e.g. "within 10-30 minutes if load continues"\n'
        '  "warning_message":  string — clear, actionable user-facing message (not alarmist)\n'
        '  "action_required":  string — what the user should do RIGHT NOW\n'
        "}"
    )

    prompt = (
        f"Current system warning:\n{current_symptom}\n\n"
        f"Past crash with similar symptoms:\n"
        f"- Type: {past_crash.get('crash_type')}\n"
        f"- Root cause: {past_crash.get('root_cause')}\n"
        f"- Preceding symptoms: {past_crash.get('symptoms')}\n\n"
        "Assess crash risk and return only JSON."
    )

    response = ask_gemma(prompt, system_prompt)

    if response.startswith("ERROR:"):
        logger.warning(f"[analyzer] Gemma unavailable for prediction: {response}")
        return _fallback_prediction(response)

    try:
        data = json.loads(_strip_json_fences(response))
        # Clamp confidence to [0, 1] in case Gemma returns something out of range
        data["confidence"] = max(0.0, min(1.0, float(data.get("confidence", 0.5))))
        return data
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        logger.warning(f"[analyzer] Prediction JSON parse failed ({e}). Raw: {response[:200]}")
        match = re.search(r"\{.*\}", response, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
                data["confidence"] = max(0.0, min(1.0, float(data.get("confidence", 0.5))))
                return data
            except Exception:
                pass
        return _fallback_prediction(response)


def _fallback_prediction(raw_response: str) -> dict:
    return {
        "confidence":      0.5,
        "time_estimate":   "Unknown",
        "warning_message": raw_response,
        "action_required": "Monitor system closely and check Ollama is running.",
    }


def summarize_crash_history(crash_history: list) -> str:
    """
    Ask Gemma for a plain-English health summary of recent crashes.
    Returns a fallback string if the history is empty or Gemma is unavailable.
    """
    if not crash_history:
        return (
            "No crash history available yet. "
            "CrashSentinel will analyse patterns as crashes are detected."
        )

    system_prompt = (
        "You are a system reliability expert writing a concise status report. "
        "Keep your response under 5 sentences. Be direct and technical but clear."
    )

    prompt = (
        f"Here is a history of recent system crashes:\n"
        f"{json.dumps(crash_history, indent=2)}\n\n"
        "Write a 3-5 sentence summary covering:\n"
        "1. The most common crash patterns\n"
        "2. Root causes that keep recurring\n"
        "3. Overall system health assessment\n"
        "4. The top 2 actionable recommendations"
    )

    result = ask_gemma(prompt, system_prompt)
    if result.startswith("ERROR:"):
        logger.warning(f"[analyzer] Summary unavailable: {result}")
        return "AI summary unavailable — check that Ollama is running (ollama serve)."
    return result


# ── Dev runner ────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(f"Testing analyzer against {OLLAMA_URL} with model {MODEL}...\n")
    test_log = (
        "kernel: Out of memory: Killed process 1234 (chrome) "
        "total-vm:4096000kB, anon-rss:3200000kB"
    )
    print(f"Log: {test_log}\n")
    result = analyze_crash(test_log)
    print(json.dumps(result, indent=2))