"""
Ollama LLM wrapper with graceful fallback.

If Ollama is not installed or not running, returns placeholder text
so the deterministic analysis still works.
"""

import os

# Flag to track Ollama availability
_ollama_available = None
_llm_instance = None

OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1:8b")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

FALLBACK_MESSAGE = "[AI narrative not available — install Ollama and run `ollama pull {model}` for AI-generated summaries. See README for setup instructions.]"


def _check_ollama():
    """Check if Ollama is running and accessible."""
    global _ollama_available
    if _ollama_available is not None:
        return _ollama_available
    try:
        import urllib.request
        req = urllib.request.Request(f"{OLLAMA_BASE_URL}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            _ollama_available = resp.status == 200
    except Exception:
        _ollama_available = False
    return _ollama_available


def get_llm():
    """Get an Ollama LLM instance, or None if unavailable."""
    global _llm_instance
    if _llm_instance is not None:
        return _llm_instance
    if not _check_ollama():
        print(f"[!] Ollama not detected at {OLLAMA_BASE_URL}.")
        print(f"  Running in deterministic-only mode (no AI narratives).")
        print(f"  To enable AI: install Ollama from https://ollama.com")
        print(f"  Then run: ollama pull {OLLAMA_MODEL}")
        return None
    try:
        from langchain_ollama import OllamaLLM
        _llm_instance = OllamaLLM(
            model=OLLAMA_MODEL,
            base_url=OLLAMA_BASE_URL,
            temperature=0.3,  # lower for more consistent output
        )
        # Quick test
        _llm_instance.invoke("test")
        print(f"[OK] Ollama connected: {OLLAMA_MODEL}")
        return _llm_instance
    except Exception as e:
        print(f"[!] Ollama error: {e}")
        _ollama_available = False
        return None


def generate(prompt: str, fallback: str = "") -> str:
    """
    Generate text using Ollama, or return fallback if unavailable.

    Args:
        prompt: The prompt to send to the LLM
        fallback: Text to return if Ollama is unavailable

    Returns:
        Generated text or fallback
    """
    llm = get_llm()
    if llm is None:
        return fallback or FALLBACK_MESSAGE.format(model=OLLAMA_MODEL)
    try:
        result = llm.invoke(prompt)
        # Basic validation: check it's not empty or error
        if result and len(result.strip()) > 20:
            return result.strip()
        return fallback or FALLBACK_MESSAGE.format(model=OLLAMA_MODEL)
    except Exception as e:
        print(f"  LLM generation error: {e}")
        return fallback or FALLBACK_MESSAGE.format(model=OLLAMA_MODEL)
