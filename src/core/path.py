from datetime import datetime
from json import load
from typing import List, Optional, Dict, Any


class PathStep:
    def __init__(
        self,
        location: str,
        timestamp: str | datetime,
        context: str = "",
        average_speed: Optional[float] = None,
        length: Optional[float] = None,
        seasonal_info: Optional[Dict[str, str]] = None,
    ):
        self.location: str = location
        self.timestamp: str = (
            timestamp if isinstance(timestamp, str) else timestamp.isoformat()
        )
        self.context: str = context
        self.average_speed: Optional[float] = average_speed
        self.length: Optional[float] = length
        self.seasonal_info: Dict[str, str] = seasonal_info or {}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PathStep":
        location = d.get("location") or ""
        timestamp = d.get("timestamp") or ""
        return cls(
            str(location),
            str(timestamp),
            d.get("context", ""),
            d.get("average_speed"),
            d.get("length"),
            d.get("seasonal_info", {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "location": self.location,
            "timestamp": self.timestamp,
            "context": self.context,
            "average_speed": self.average_speed,
            "length": self.length,
            "seasonal_info": self.seasonal_info,
        }

    def to_prompt(self) -> str:
        line: str = f"- {self.location} at {self.timestamp}: {self.context}"
        extra: List[str] = []
        if self.average_speed is not None:
            extra.append(f"average speed: {self.average_speed} km/h")
        if self.length is not None:
            extra.append(f"length: {self.length} m")
        if self.seasonal_info:
            seasons = ", ".join(
                f"{season}: {desc}" for season, desc in self.seasonal_info.items()
            )
            extra.append(f"seasonal info: [{seasons}]")
        if extra:
            line += " [" + ", ".join(extra) + "]"
        return line


class Path:
    def __init__(self, steps: Optional[List[PathStep]] = None, description: str = ""):
        self.steps: List[PathStep] = steps or []
        self.description: str = description

    @classmethod
    def from_json_file(cls, filepath: str, index: int = 0) -> "Path":
        with open(filepath, "r") as f:
            data = load(f)
        scenario = data[index]
        steps = [PathStep.from_dict(step) for step in scenario["steps"]]
        return cls(steps, scenario.get("description", ""))

    def add_step(self, step: PathStep) -> None:
        self.steps.append(step)

    def to_prompt(self) -> str:
        return "\n".join(step.to_prompt() for step in self.steps)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "description": self.description,
            "steps": [step.to_dict() for step in self.steps],
        }
