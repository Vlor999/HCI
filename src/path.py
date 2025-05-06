from datetime import datetime
import json

class Path:
    def __init__(self):
        self.steps = []

    def add_step(self, location, timestamp, context="", average_speed=None, length=None, seasonal_info=None):
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
        if seasonal_info is not None:
            step["seasonal_info"] = seasonal_info
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
                step.get("length"),
                step.get("seasonal_info")
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
                step.get("length"),
                step.get("seasonal_info")
            )
        return path

    def to_prompt(self):
        lines = []
        for step in self.steps:
            line = (
                f"- {step['location']} at {step['timestamp']}: {step.get('context', '')}"
            )
            extra = []
            if "average_speed" in step:
                extra.append(f"average speed: {step['average_speed']} km/h")
            if "length" in step:
                extra.append(f"length: {step['length']} m")
            if "seasonal_info" in step:
                seasons = ", ".join(
                    f"{season}: {desc}" for season, desc in step["seasonal_info"].items()
                )
                extra.append(f"seasonal info: [{seasons}]")
            if extra:
                line += " [" + ", ".join(extra) + "]"
            lines.append(line)
        return "\n".join(lines)

    def __len__(self):
        return len(self.steps)

    def __getitem__(self, idx):
        return self.steps[idx]
