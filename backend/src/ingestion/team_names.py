from __future__ import annotations

import re

TEAM_ACRONYMS = {
    "ai": "AI",
    "api": "API",
    "ml": "ML",
    "qa": "QA",
    "sre": "SRE",
    "ui": "UI",
    "ux": "UX",
}

INVALID_TEAM_PREFIXES = {
    "a",
    "an",
    "any",
    "at",
    "current",
    "do",
    "for",
    "from",
    "her",
    "his",
    "its",
    "meet",
    "my",
    "no",
    "our",
    "part",
    "questions",
    "reach",
    "see",
    "some",
    "that",
    "the",
    "their",
    "these",
    "this",
    "those",
    "with",
    "your",
}

EXPLICIT_TEAM_PATTERNS = [
    re.compile(r"(?im)^\s*Owned by:\s*([A-Za-z][A-Za-z0-9/& _-]{0,60}? team)\b"),
    re.compile(r"(?im)^\s*#+\s*Team:\s*([A-Za-z][A-Za-z0-9/& _-]{0,60}? team)\b"),
    re.compile(r"(?im)(?:^|\|)\s*Team:\s*([A-Za-z][A-Za-z0-9/& _-]{0,60}? team)\b"),
    re.compile(r"(?im)\bmaintained by(?: the)? ([A-Za-z][A-Za-z0-9/& _-]{0,60}? team)\b"),
    re.compile(r"(?im)\bpart of the ([A-Za-z][A-Za-z0-9/& _-]{0,60}? team)(?:'s)?\b"),
    re.compile(r"(?im)\b([A-Za-z][A-Za-z0-9/& _-]{0,60}? team)\s+(?:owns|is responsible for|maintains|reviews|audits)\b"),
]

PATH_TEAM_PATTERN = re.compile(r"(?<![A-Za-z0-9])([a-z0-9]+(?:-[a-z0-9]+)*-team)(?=/)", re.IGNORECASE)


def canonicalize_team_name(name: str) -> str | None:
    cleaned = name.strip().strip(".,:;()[]{}")
    if not cleaned:
        return None

    cleaned = cleaned.replace("&amp;", "&")
    cleaned = cleaned.replace("_", " ").replace("-", " ")
    cleaned = re.sub(r"[^A-Za-z0-9/& ]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return None

    tokens = cleaned.lower().split()
    if len(tokens) < 2 or tokens[-1] != "team":
        return None

    if len(tokens) > 4:
        return None

    if tokens[0] in INVALID_TEAM_PREFIXES:
        return None

    normalized_tokens: list[str] = []
    for token in tokens:
        if token == "team":
            normalized_tokens.append("Team")
            continue
        if token in TEAM_ACRONYMS:
            normalized_tokens.append(TEAM_ACRONYMS[token])
            continue
        if token == "&":
            normalized_tokens.append("&")
            continue
        normalized_tokens.append(token.capitalize())

    return " ".join(normalized_tokens)


def extract_explicit_team_names(content: str, source_path: str = "") -> list[str]:
    candidates: list[str] = []

    for pattern in EXPLICIT_TEAM_PATTERNS:
        candidates.extend(match.group(1) for match in pattern.finditer(content))

    for match in PATH_TEAM_PATTERN.finditer(source_path):
        candidates.append(match.group(1))

    normalized: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        canonical = canonicalize_team_name(candidate)
        if not canonical:
            continue
        key = canonical.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(canonical)

    return normalized
