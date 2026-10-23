"""LLM access. Two wire formats cover almost every provider:

* ``anthropic``: Anthropic's native Messages API (Claude).
* ``openai``:    the OpenAI Chat Completions format, which OpenAI itself, DeepSeek,
                 Kimi (Moonshot), Qwen (DashScope), Gemini's compatibility endpoint,
                 Ollama, vLLM and many others all speak.

Plus ``mock`` for demos and tests (no network, no API key).
API keys come from environment variables only.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests

# Defaults are only starting points: model names change often, so override them with
# `model:` in blogpub.yml or `--model` whenever your provider has newer ones.
PRESETS: Dict[str, Dict[str, Any]] = {
    "openai": {
        "kind": "openai", "base_url": "https://api.openai.com/v1", "api_key_env": "OPENAI_API_KEY",
        "model": "gpt-4o", "vision": True, "token_param": "max_completion_tokens", "json_mode": True,
        "label": "OpenAI (ChatGPT)",
    },
    "anthropic": {
        "kind": "anthropic", "base_url": "https://api.anthropic.com", "api_key_env": "ANTHROPIC_API_KEY",
        "model": "claude-sonnet-5-5", "vision": True, "label": "Anthropic (Claude)",
    },
    "deepseek": {
        "kind": "openai", "base_url": "https://api.deepseek.com", "api_key_env": "DEEPSEEK_API_KEY",
        "model": "deepseek-chat", "vision": False, "token_param": "max_tokens", "json_mode": True,
        "label": "DeepSeek",
    },
    "kimi": {
        "kind": "openai", "base_url": "https://api.moonshot.cn/v1", "api_key_env": "MOONSHOT_API_KEY",
        "model": "moonshot-v1-32k", "vision": False, "token_param": "max_tokens", "json_mode": True,
        "label": "Kimi (Moonshot AI)",
    },
    "qwen": {
        "kind": "openai", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key_env": "DASHSCOPE_API_KEY", "model": "qwen-plus", "vision": False,
        "token_param": "max_tokens", "json_mode": True, "label": "Qwen (Alibaba DashScope)",
    },
    "ollama": {
        "kind": "openai", "base_url": "http://localhost:11434/v1", "api_key_env": None,
        "model": "llama3.1", "vision": False, "token_param": "max_tokens", "json_mode": False,
        "label": "Ollama (local, no key)",
    },
    "custom": {
        "kind": "openai", "base_url": None, "api_key_env": "LLM_API_KEY", "model": None, "vision": False,
        "token_param": "max_tokens", "json_mode": False,
        "label": "Any OpenAI-compatible endpoint (set base_url and model)",
    },
    "mock": {
        "kind": "mock", "base_url": None, "api_key_env": None, "model": "mock", "vision": False,
        "label": "Offline mock, for demos and tests",
    },
}


class ProviderError(Exception):
    pass


@dataclass
class Image:
    """An image to show the model (already downscaled)."""
    name: str
    media_type: str
    data_b64: str


@dataclass
class Provider:
    name: str
    kind: str
    model: str
    base_url: Optional[str] = None
    api_key_env: Optional[str] = None
    vision: bool = False
    token_param: str = "max_tokens"
    json_mode: bool = False
    timeout: int = 180
    max_tokens: int = 8000
    extra: Dict[str, Any] = field(default_factory=dict)

    # ---- helpers -------------------------------------------------------
    def _key(self) -> Optional[str]:
        if not self.api_key_env:
            return None
        key = os.environ.get(self.api_key_env)
        if not key:
            raise ProviderError(
                f"Environment variable {self.api_key_env} is not set. Export your API key first, e.g.\n"
                f"    export {self.api_key_env}='...'"
            )
        return key

    def _redact(self, text: str) -> str:
        key = os.environ.get(self.api_key_env or "", "")
        return text.replace(key, "***") if key else text

    def _post(self, url: str, headers: Dict[str, str], payload: Dict[str, Any]) -> Dict[str, Any]:
        last = ""
        for attempt in range(3):
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
            except requests.RequestException as e:
                last = self._redact(str(e))
            else:
                if resp.status_code < 400:
                    try:
                        return resp.json()
                    except ValueError:
                        raise ProviderError("The provider returned a response that is not JSON")
                last = f"HTTP {resp.status_code}: {self._redact(resp.text[:500])}"
                if resp.status_code not in (408, 429, 500, 502, 503, 504, 529):
                    break  # retrying will not help (bad key, bad model name, ...)
            time.sleep(2 ** attempt)
        raise ProviderError(f"{self.name} request failed: {last}")

    # ---- the one method the rest of the program uses -------------------
    def complete(self, system: str, user: str, images: Optional[List[Image]] = None) -> str:
        images = images or []
        if self.kind == "mock":
            return _mock_reply(user, [i.name for i in images])
        if self.kind == "anthropic":
            return self._anthropic(system, user, images)
        if self.kind == "openai":
            return self._openai(system, user, images)
        raise ProviderError(f"Unknown provider kind: {self.kind}")

    def _anthropic(self, system: str, user: str, images: List[Image]) -> str:
        content: List[Dict[str, Any]] = [
            {"type": "image", "source": {"type": "base64", "media_type": i.media_type, "data": i.data_b64}}
            for i in images
        ]
        content.append({"type": "text", "text": user})
        data = self._post(
            f"{(self.base_url or '').rstrip('/')}/v1/messages",
            {"x-api-key": self._key() or "", "anthropic-version": "2023-06-01", "content-type": "application/json"},
            {"model": self.model, "max_tokens": self.max_tokens, "system": system,
             "messages": [{"role": "user", "content": content}]},
        )
        parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
        if not parts:
            raise ProviderError(f"No text in the response: {json.dumps(data)[:300]}")
        return "".join(parts)

    def _openai(self, system: str, user: str, images: List[Image]) -> str:
        if images:
            content: Any = [{"type": "text", "text": user}] + [
                {"type": "image_url", "image_url": {"url": f"data:{i.media_type};base64,{i.data_b64}"}}
                for i in images
            ]
        else:
            content = user
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}],
            self.token_param: self.max_tokens,
        }
        if self.json_mode:
            payload["response_format"] = {"type": "json_object"}
        headers = {"content-type": "application/json"}
        key = self._key()
        if key:
            headers["authorization"] = f"Bearer {key}"
        data = self._post(f"{(self.base_url or '').rstrip('/')}/chat/completions", headers, payload)
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            raise ProviderError(f"Unexpected response shape: {json.dumps(data)[:300]}")


def make_provider(cfg: Dict[str, Any]) -> Provider:
    name = cfg["provider"]
    if name not in PRESETS:
        raise ProviderError(f"Unknown provider '{name}'. Choose one of: {', '.join(PRESETS)}")
    preset = PRESETS[name]

    def pick(key: str):
        return cfg[key] if cfg.get(key) is not None else preset.get(key)

    model = pick("model")
    base_url = pick("base_url")
    if preset["kind"] != "mock":
        if not model:
            raise ProviderError(f"Provider '{name}' needs a model: set `model:` in blogpub.yml or pass --model")
        if not base_url:
            raise ProviderError(f"Provider '{name}' needs a base_url: set `base_url:` in blogpub.yml")
    return Provider(
        name=name, kind=preset["kind"], model=model or "mock", base_url=base_url,
        api_key_env=pick("api_key_env"), vision=bool(pick("vision")),
        token_param=preset.get("token_param", "max_tokens"), json_mode=bool(preset.get("json_mode", False)),
        timeout=int(cfg.get("timeout", 180)),
    )


# ---- offline mock ---------------------------------------------------------
def _mock_reply(user: str, image_names: List[str]) -> str:
    """A deterministic stand-in for a model: reads the prompt's markers and returns valid JSON."""
    notes = re.search(r"<<<NOTES\n(.*?)\nNOTES>>>", user, re.S)
    notes_text = notes.group(1).strip() if notes else "Untitled"
    langs = re.search(r"LANGUAGES: (.+)", user)
    languages = [x.strip() for x in langs.group(1).split(",")] if langs else ["en"]
    block = re.search(r"<<<IMAGES\n(.*?)\nIMAGES>>>", user, re.S)
    imgs = re.findall(r"^- (\S+)", block.group(1), re.M) if block else []
    first = next((ln.strip("# ").strip() for ln in notes_text.splitlines() if ln.strip()), "Untitled")
    body_imgs = "\n\n".join(f"![{n}](IMG:{n})" for n in imgs)
    posts = {}
    for lang in languages:
        body = f"{notes_text}\n\n{body_imgs}".strip() if lang == languages[0] else (
            f"(mock translation to {lang})\n\n{notes_text}\n\n{body_imgs}".strip())
        posts[lang] = {"title": first if lang == languages[0] else f"{first} ({lang})", "body": body}
    return json.dumps({
        "slug": re.sub(r"[^a-z0-9]+", "-", first.lower()).strip("-") or "mock-post",
        "categories": {l: ["Notes"] for l in languages},
        "tags": {l: ["mock"] for l in languages},
        "posts": posts,
    })
