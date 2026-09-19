"""Decide which game a listing belongs to, and whether it is a pre-order."""
from __future__ import annotations

import re

# Title/tag wording shops actually use. "Pre-Sale" counts; "Pre-Owned" must not.
PREORDER_RE = re.compile(r"\bpre[\s\-]?(order|sale)s?\b|\bpreorders?\b|\bpresale\b", re.I)

# Body text is noisy (many shops print a generic pre-order policy on every page),
# so only these stronger phrasings count when they appear in the description.
BODY_PREORDER_RE = re.compile(
    r"pre[\s\-]?order\s+(available|now open|period|item|product)|this (item|product) is a pre[\s\-]?order",
    re.I,
)

DEFAULT_GAMES = {
    "Pokemon":   r"pok[eé]mon|\bptcg\b",
    "One Piece": r"one\s*piece|\b(OP|EB|PRB|ST)[\s\-]?\d{2}\b",
    "Riftbound": r"riftbound",
    "Topps":     r"\btopps\b|\bbowman\b",
    "Lorcana":   r"lorcana",
    "Magic":     r"magic:?\s*the\s*gathering|\bmtg\b",
    "Gundam":    r"gundam",
}


def compile_games(games: dict | None) -> dict:
    return {k: re.compile(v, re.I) for k, v in (games or DEFAULT_GAMES).items()}


def classify(text: str, games: dict) -> str | None:
    """First matching game wins, in config order. None = not a game we watch."""
    for name, rx in games.items():
        if rx.search(text or ""):
            return name
    return None


def is_preorder(title: str, tags, body: str = "") -> bool:
    tag_text = " ".join(tags) if isinstance(tags, (list, tuple)) else (tags or "")
    if PREORDER_RE.search(title or "") or PREORDER_RE.search(tag_text):
        return True
    return bool(BODY_PREORDER_RE.search(body or ""))
