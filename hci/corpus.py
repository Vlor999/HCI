"""Turns everything in data/ into retrievable chunks."""

import json
import re
from dataclasses import dataclass
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
FACTS = DATA / "facts.json"


@dataclass(frozen=True)
class Chunk:
    id: str
    text: str
    source: str  # path | manual | correction | example | fact
    scenario: int | None = None


def stamp() -> float:
    """Latest change in data/, so a running server picks up edits made elsewhere."""
    return max(f.stat().st_mtime for f in DATA.rglob("*") if f.is_file())


def scenarios() -> list[dict]:
    return json.loads((DATA / "paths.json").read_text())


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
    return json.loads(FACTS.read_text()) if FACTS.exists() else []


def add_fact(text: str, scenario: int | None) -> None:
    FACTS.write_text(json.dumps(load_facts() + [{"text": text, "scenario": scenario}], indent=2))


def load() -> list[Chunk]:
    chunks = [
        Chunk(f"path-{i}-{s['location']}", step_text(sc.get("description", f"#{i}"), s), "path", i)
        for i, sc in enumerate(scenarios())
        for s in sc["steps"]
    ]

    manual = (DATA / "documents" / "sample_manual.md").read_text()
    for n, section in enumerate(re.split(r"\n(?=\d+\. )", manual.strip())):
        chunks.append(Chunk(f"manual-{n + 1}", "Robot manual. " + " ".join(section.split()), "manual"))

    for f in sorted((DATA / "corrections").glob("*.md")):
        text = f.read_text()
        q = re.search(r"^### Q\d+: (.+)$", text, re.MULTILINE)
        sol = re.split(r"^### correct solution\s*$", text, flags=re.MULTILINE | re.IGNORECASE)
        if len(sol) == 2:
            question = f"Question: {q[1]} " if q else ""
            body = " ".join(sol[1].split())
            chunks.append(
                Chunk(f"correction-{f.stem}", f"Past mistake. {question}Expected answer: {body}", "correction")
            )

    for n, ex in enumerate(json.loads((DATA / "explanations" / "sample_explanations.json").read_text())):
        chunks.append(Chunk(f"example-{n}", f"Example explanation. Q: {ex['Input']} A: {ex['Output']}", "example"))

    for n, fact in enumerate(load_facts()):
        chunks.append(Chunk(f"fact-{n}", f"Operator update: {fact['text']}", "fact", fact.get("scenario")))
    return chunks
