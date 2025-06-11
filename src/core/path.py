from datetime import datetime
from json import load
from typing import List, Optional, Dict, Any, Union


class PathStep:
    def __init__(
        self,
        location: str,
        timestamp: str | datetime,
        context: str = "",
        average_speed: Optional[float] = None,
        length: Optional[float] = None,
        terrain_features: Optional[Dict[str, str]] = None,
        energy_consumption: Optional[str] = None,
        ecological_impact: Optional[str] = None,
        seasonal_info: Optional[Union[str, Dict[str, str]]] = None,
        hash_value: Optional[int] = None,
    ):
        self.location: str = location
        self.timestamp: str = timestamp if isinstance(timestamp, str) else timestamp.isoformat()
        self.context: str = context
        self.average_speed: Optional[float] = average_speed
        self.length: Optional[float] = length
        self.terrain_features: Dict[str, str] = terrain_features or {}
        self.energy_consumption: Optional[str] = energy_consumption
        self.ecological_impact: Optional[str] = ecological_impact
        self.hash_value: Optional[int] = hash_value

        if isinstance(seasonal_info, str):
            self.seasonal_info = {"info": seasonal_info}
        else:
            self.seasonal_info = seasonal_info or {}

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
            d.get("terrain_features"),
            d.get("energy_consumption"),
            d.get("ecological_impact"),
            d.get("seasonal_info", {}),
            d.get("hash_value", 0),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "location": self.location,
            "timestamp": self.timestamp,
            "context": self.context,
            "average_speed": self.average_speed,
            "length": self.length,
            "terrain_features": self.terrain_features,
            "energy_consumption": self.energy_consumption,
            "ecological_impact": self.ecological_impact,
            "seasonal_info": self.seasonal_info,
            "hash_value": self.hash_value,
        }

    def to_prompt(self) -> str:
        line: str = f"- {self.location} at {self.timestamp}: {self.context}"
        extra: List[str] = []
        if self.average_speed is not None:
            extra.append(f"average speed: {self.average_speed} km/h")
        if self.length is not None:
            extra.append(f"length: {self.length} m")

        if self.terrain_features:
            tf_parts = [f"{k}: {v}" for k, v in self.terrain_features.items()]
            extra.append(f"terrain: [{', '.join(tf_parts)}]")

        if self.energy_consumption:
            extra.append(f"energy: {self.energy_consumption}")

        if self.ecological_impact:
            extra.append(f"eco-impact: {self.ecological_impact}")

        if self.seasonal_info:
            if "info" in self.seasonal_info:
                extra.append(f"season: {self.seasonal_info['info']}")
            else:
                seasons = ", ".join(f"{season}: {desc}" for season, desc in self.seasonal_info.items())
                extra.append(f"seasonal info: [{seasons}]")

        if self.hash_value:
            extra.append(f"Hash: {self.hash_value}")

        if extra:
            line += " [" + ", ".join(extra) + "]"
        return line


class Path:
    def __init__(self, steps: Optional[List[PathStep]] = None, description: str = "", hash_value: int = 0):
        self.steps: List[PathStep] = steps or []
        self.description: str = description
        self.hash_value: int = hash_value

    @classmethod
    def from_json_file(cls, filepath: str, index: int = 0) -> "Path":
        with open(filepath, "r") as f:
            data = load(f)
        scenario = data[index]
        steps = [PathStep.from_dict(step) for step in scenario["steps"]]
        return cls(steps, scenario.get("description", ""), scenario.get("hash_value"))

    def add_step(self, step: PathStep) -> None:
        self.steps.append(step)

    def to_prompt(self) -> str:
        return "\n".join(step.to_prompt() for step in self.steps)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "description": self.description,
            "hash": self.hash_value,
            "steps": [step.to_dict() for step in self.steps],
        }
