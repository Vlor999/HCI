"""Turns everything in data/ into retrievable chunks, and stores operator-approved facts."""

import json
import os
import re
import tempfile
import time
from pathlib import Path

from loguru import logger

from hci.config import get_settings
from hci.constants import CORRECTIONS_DIR, DATA_DIR, EXPLANATIONS_FILE, MANUAL_FILE, PATHS_FILE, ROOT_DIR, Source
from hci.types import RecordChunk


def file_ref(path: Path) -> str:
    """Reference to a file for chunk ids: its path relative to the repo root, or absolute outside the repo.

    Args:
        path: The file.

    Returns:
        The POSIX path, e.g. `data/paths.json`.
    """
    path = path.resolve()
    return path.relative_to(ROOT_DIR).as_posix() if path.is_relative_to(ROOT_DIR) else path.as_posix()


def stamp() -> float:
    """Latest change in data/ and the facts file, so a running server picks up edits made elsewhere.

    Returns:
        The newest modification time under `DATA_DIR` or of the facts file, 0.0 when none exists.
    """
    files = [f for f in DATA_DIR.rglob("*") if f.is_file()] + [get_settings().facts_file]
    return max((f.stat().st_mtime for f in files if f.exists()), default=0.0)


def scenarios() -> list[dict]:
    """Recorded scenarios.

    Returns:
        One dict per scenario, with its `description` and `steps` (one per path).
    """
    return json.loads(PATHS_FILE.read_text())


def step_text(desc: str, s: dict) -> str:
    """Render one path step as a self-contained passage, with the travel time precomputed.

    Args:
        desc: Description of the scenario the step belongs to.
        s: The step record from `paths.json`.

    Returns:
        The passage text.
    """
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

    A corrupt file is renamed to `facts.json.corrupt-<timestamp>`, so the next `add_fact` cannot overwrite it.

    Returns:
        The facts as `{text, scenario}` dicts; empty when the file is missing, unreadable or corrupt.
    """
    facts = get_settings().facts_file
    if not facts.exists():
        return []
    try:
        return json.loads(facts.read_text())
    except OSError as e:
        logger.warning("Ignoring unreadable facts file {}: {}", facts, e)
        return []
    except json.JSONDecodeError as e:
        backup = facts.with_name(f"{facts.name}.corrupt-{time.strftime('%Y%m%d-%H%M%S')}")
        facts.replace(backup)
        logger.warning("Corrupt facts file {} moved to {}: {}", facts, backup, e)
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


def _load_paths() -> list[RecordChunk]:
    return [
        RecordChunk(
            f"{file_ref(PATHS_FILE)}#{i}/{s['location']}", step_text(sc.get("description", f"#{i}"), s), Source.PATH, i
        )
        for i, sc in enumerate(scenarios())
        for s in sc["steps"]
    ]


def _load_manual() -> list[RecordChunk]:
    sections = re.split(r"\n(?=\d+\. )", MANUAL_FILE.read_text().strip())
    return [
        RecordChunk(f"{file_ref(MANUAL_FILE)}#{n + 1}", "Robot manual. " + " ".join(section.split()), Source.MANUAL)
        for n, section in enumerate(sections)
    ]


def _load_correction(path: Path) -> RecordChunk | None:
    text = path.read_text()
    q = re.search(r"^### Q\d+: (.+)$", text, re.MULTILINE)
    sol = re.split(r"^### correct solution\s*$", text, flags=re.MULTILINE | re.IGNORECASE)
    if len(sol) != 2:
        return None
    question = f"Question: {q[1]} " if q else ""
    body = " ".join(sol[1].split())
    return RecordChunk(file_ref(path), f"Past mistake. {question}Expected answer: {body}", Source.CORRECTION)


def _load_corrections() -> list[RecordChunk]:
    return [c for f in sorted(CORRECTIONS_DIR.glob("*.md")) if (c := _load_correction(f))]


def _load_examples() -> list[RecordChunk]:
    return [
        RecordChunk(
            f"{file_ref(EXPLANATIONS_FILE)}#{n}",
            f"Example explanation. Q: {ex['Input']} A: {ex['Output']}",
            Source.EXAMPLE,
        )
        for n, ex in enumerate(json.loads(EXPLANATIONS_FILE.read_text()))
    ]


def _load_facts() -> list[RecordChunk]:
    return [
        RecordChunk(f"fact-{n}", f"Operator update: {fact['text']}", Source.FACT, fact.get("scenario"))
        for n, fact in enumerate(load_facts())
    ]


def load() -> list[RecordChunk]:
    """Every record as retrievable chunks: paths, manual, corrections, examples, then operator facts.

    Returns:
        The chunks, in that source order.
    """
    return _load_paths() + _load_manual() + _load_corrections() + _load_examples() + _load_facts()
