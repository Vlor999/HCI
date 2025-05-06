from datetime import datetime
import json

class PathStep:
    def __init__(self, location, timestamp, context="", average_speed=None, length=None, seasonal_info=None):
        self.location = location
        self.timestamp = timestamp if isinstance(timestamp, str) else timestamp.isoformat()
        self.context = context
        self.average_speed = average_speed
        self.length = length
        self.seasonal_info = seasonal_info or {}

    @classmethod
    def from_dict(cls, d):
        return cls(
            d.get("location"),
            d.get("timestamp"),
            d.get("context", ""),
            d.get("average_speed"),
            d.get("length"),
            d.get("seasonal_info", {})
        )

    def to_dict(self):
        return {
            "location": self.location,
            "timestamp": self.timestamp,
            "context": self.context,
            "average_speed": self.average_speed,
            "length": self.length,
            "seasonal_info": self.seasonal_info
        }

    def to_prompt(self):
        line = f"- {self.location} at {self.timestamp}: {self.context}"
        extra = []
        if self.average_speed is not None:
            extra.append(f"average speed: {self.average_speed} km/h")
        if self.length is not None:
            extra.append(f"length: {self.length} m")
        if self.seasonal_info:
            seasons = ", ".join(f"{season}: {desc}" for season, desc in self.seasonal_info.items())
            extra.append(f"seasonal info: [{seasons}]")
        if extra:
            line += " [" + ", ".join(extra) + "]"
        return line

class Path:
    def __init__(self, steps=None, description=""):
        self.steps = steps or []
        self.description = description

    @classmethod
    def from_json_file(cls, filepath, index=0):
        with open(filepath, "r") as f:
            data = json.load(f)
        scenario = data[index]
        steps = [PathStep.from_dict(step) for step in scenario["steps"]]
        return cls(steps, scenario.get("description", ""))

    def add_step(self, step):
        self.steps.append(step)

    def to_prompt(self):
        return "\n".join(step.to_prompt() for step in self.steps)

    def to_dict(self):
        return {
            "description": self.description,
            "steps": [step.to_dict() for step in self.steps]
        }
