"""عميل Claude Messages API باستخدام المكتبة القياسية فقط."""
import json
import urllib.error
import urllib.request

API_URL = "https://api.anthropic.com/v1/messages"


def call_claude(api_key: str, model: str, system: str, messages: list[dict], max_tokens: int = 800) -> str:
    body = json.dumps({
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": messages,
    }).encode("utf-8")
    req = urllib.request.Request(
        API_URL,
        data=body,
        method="POST",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print("Anthropic refused:", e.read().decode("utf-8", "replace"))
        raise
    return "".join(block.get("text", "") for block in data.get("content", []) if block.get("type") == "text")
