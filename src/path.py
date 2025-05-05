from datetime import datetime
import json
import os

class Path:
    def __init__(self):
        self.steps = []

    def add_step(self, location, timestamp, context="", average_speed=None, length=None):
        if isinstance(timestamp, datetime):
            timestamp = timestamp.isoformat()
        step = {
            "location": location,
            "timestamp": timestamp,
            "context": context
        }
        if average_speed is not None:
            step["average_speed"] = average_speed
        if length is not None:
            step["length"] = length
        self.steps.append(step)

    @classmethod
    def from_list(cls, steps):
        path = cls()
        for step in steps:
            path.add_step(
                step["location"],
                step["timestamp"],
                step.get("context", ""),
                step.get("average_speed"),
                step.get("length")
            )
        return path

    @classmethod
    def from_json_file(cls, filepath, index=0):
        with open(filepath, "r") as f:
            data = json.load(f)
        steps = data[index]["steps"]
        path = cls()
        for step in steps:
            ts = step["timestamp"]
            if isinstance(ts, str):
                try:
                    ts = datetime.fromisoformat(ts)
                except Exception:
                    pass
            path.add_step(
                step["location"],
                ts,
                step.get("context", ""),
                step.get("average_speed"),
                step.get("length")
            )
        return path

    def to_prompt(self):
        lines = []
        for step in self.steps:
            line = (
                f"- {step['location']} at {step['timestamp']}: {step.get('context', '')}"
            )
            # Add extra info if available
            if "average_speed" in step or "length" in step:
                extra = []
                if "average_speed" in step:
                    extra.append(f"average speed: {step['average_speed']} km/h")
                if "length" in step:
                    extra.append(f"length: {step['length']} m")
                line += " [" + ", ".join(extra) + "]"
            lines.append(line)
        return "\n".join(lines)

    def __len__(self):
        return len(self.steps)

    def __getitem__(self, idx):
        return self.steps[idx]
