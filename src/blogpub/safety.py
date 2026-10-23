"""Privacy checks. Run on your notes BEFORE they are sent to an LLM provider, and again on
the finished post BEFORE it is published. Findings never contain the full secret."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Pattern, Tuple

BLOCK = "block"  # never send / publish without an explicit override
WARN = "warn"    # ask the author to confirm


@dataclass
class Finding:
    level: str
    kind: str
    line: int
    preview: str  # masked

    def __str__(self) -> str:
        return f"[{self.level}] line {self.line}: {self.kind}: {self.preview}"


def _mask(text: str) -> str:
    text = text.strip()
    if len(text) <= 8:
        return text[:2] + "***"
    return text[:4] + "***" + text[-2:]


_RULES: List[Tuple[str, str, Pattern[str]]] = [
    (BLOCK, "private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    (BLOCK, "API key (sk-...)", re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}")),
    (BLOCK, "GitHub token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}|\bgithub_pat_[A-Za-z0-9_]{30,}")),
    (BLOCK, "AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    (BLOCK, "Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}")),
    (BLOCK, "Google API key", re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}")),
    (WARN, "password or secret assignment", re.compile(
        r"(?i)\b(?:password|passwd|secret|token|api[_-]?key)\b\s*[:=]\s*['\"]?[^\s'\"<>]{6,}")),
    (WARN, "IPv4 address", re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")),
    (WARN, "email address", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
    (WARN, "mainland China mobile number", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
    (WARN, "ssh target (user@host)", re.compile(r"\bssh\s+(?:-\S+\s+)*[A-Za-z0-9_.\-]+@[A-Za-z0-9.\-]+")),
    (WARN, "home directory path", re.compile(r"(?:/Users/|/home/|C:\\Users\\)[A-Za-z0-9_.\-]+")),
]

# Documentation-style addresses that are fine to publish.
_SAFE_IPS = {"0.0.0.0", "127.0.0.1", "255.255.255.255"}
_SAFE_EMAIL_DOMAINS = {"example.com", "example.org", "example.net", "users.noreply.github.com"}


def scan(text: str) -> List[Finding]:
    findings: List[Finding] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        for level, kind, pattern in _RULES:
            for m in pattern.finditer(line):
                hit = m.group(0)
                if kind == "IPv4 address" and (hit in _SAFE_IPS or hit.startswith(("192.0.2.", "198.51.100.", "203.0.113."))):
                    continue
                if kind == "email address" and hit.split("@")[-1].lower() in _SAFE_EMAIL_DOMAINS:
                    continue
                findings.append(Finding(level, kind, lineno, _mask(hit)))
    return findings


def worst(findings: List[Finding]) -> str:
    if any(f.level == BLOCK for f in findings):
        return BLOCK
    return WARN if findings else ""
