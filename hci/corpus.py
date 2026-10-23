"""Turns everything in data/ into retrievable chunks."""

import json
import os
import re
import tempfile

from loguru import logger

from hci.config import get_settings
from hci.constants import CORRECTIONS_DIR, DATA_DIR, EXPLANATIONS_FILE, MANUAL_FILE, PATHS_FILE, Source
from hci.types import RecordChunk


def stamp() -> float:
    """Latest change in data/, so a running server picks up edits made elsewhere.

    Returns:
        The newest file modification time under `DATA_DIR`, 0.0 when it holds no file.
    """
    return max((f.stat().st_mtime for f in DATA_DIR.rglob("*") if f.is_file()), default=0.0)


def scenarios() -> list[dict]:
    return json.loads(PATHS_FILE.read_text())


def step_text(desc: str, s: dict) -> str:
    parts = [
        f"Scenario '{desc}', path {s['location']} (last passage {s.get('timestamp', '?')}): {s.get('context', '')}"
    ]
    length, speed = s.get("length"), s.get("average_speed")
    if length and speed:
        # LLMs get t = d / v wrong (see data/corrections), so compute it here
        parts.append(
            f"Length {length} m, average speed {speed} km/h, travel time {length / 1000 / speed * 60:.1f} min."
        )
    if s.get("terrain_features"):
        parts.append("Terrain: " + ", ".join(f"{k} {v}" for k, v in s["terrain_features"].items()) + ".")
    for key in ("energy_consumption", "ecological_impact"):
        if s.get(key):
            parts.append(f"{key.replace('_', ' ').capitalize()}: {s[key]}.")
    season = s.get("seasonal_info")
    if season:
        season = season if isinstance(season, str) else "; ".join(f"{k}: {v}" for k, v in season.items())
        parts.append(f"Season: {season}.")
    return " ".join(parts)


def load_facts() -> list[dict]:
    """Operator-approved facts.

    Returns:
        The facts as `{text, scenario}` dicts; empty when the file is missing or corrupt.
    """
    facts = get_settings().facts_file
    if not facts.exists():
        return []
    try:
        return json.loads(facts.read_text())
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Ignoring unreadable facts file {}: {}", facts, e)
        return []


def add_fact(text: str, scenario: int | None) -> None:
    """Append an approved fact, atomically: a crash mid-write leaves the old file intact.

    Args:
        text: The fact, one self-contained sentence.
        scenario: Scenario it applies to; None for everywhere.
    """
    facts = get_settings().facts_file
    payload = json.dumps(load_facts() + [{"text": text, "scenario": scenario}], indent=2)
    with tempfile.NamedTemporaryFile("w", dir=facts.parent, suffix=".tmp", delete=False) as tmp:
        tmp.write(payload)
    os.replace(tmp.name, facts)


def load() -> list[RecordChunk]:
    chunks = [
        RecordChunk(f"path-{i}-{s['location']}", step_text(sc.get("description", f"#{i}"), s), Source.PATH, i)
        for i, sc in enumerate(scenarios())
        for s in sc["steps"]
    ]

    manual = MANUAL_FILE.read_text()
    for n, section in enumerate(re.split(r"\n(?=\d+\. )", manual.strip())):
        chunks.append(RecordChunk(f"manual-{n + 1}", "Robot manual. " + " ".join(section.split()), Source.MANUAL))

    for f in sorted(CORRECTIONS_DIR.glob("*.md")):
        text = f.read_text()
        q = re.search(r"^### Q\d+: (.+)$", text, re.MULTILINE)
        sol = re.split(r"^### correct solution\s*$", text, flags=re.MULTILINE | re.IGNORECASE)
        if len(sol) == 2:
            question = f"Question: {q[1]} " if q else ""
            body = " ".join(sol[1].split())
            chunks.append(
                RecordChunk(
                    f"correction-{f.stem}", f"Past mistake. {question}Expected answer: {body}", Source.CORRECTION
                )
            )

    for n, ex in enumerate(json.loads(EXPLANATIONS_FILE.read_text())):
        chunks.append(
            RecordChunk(f"example-{n}", f"Example explanation. Q: {ex['Input']} A: {ex['Output']}", Source.EXAMPLE)
        )

    for n, fact in enumerate(load_facts()):
        chunks.append(RecordChunk(f"fact-{n}", f"Operator update: {fact['text']}", Source.FACT, fact.get("scenario")))
    return chunks
