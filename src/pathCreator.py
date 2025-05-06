from datetime import datetime
from src.path import Path
from typing import List, Optional, Callable, Any
from typeguard import typechecked

def create_custom_path():
    print("\nLet's create a custom path. Enter each step's details. Leave location empty to finish.")
    path = Path()
    while True:
        location = input("Location name (leave empty to finish): ").strip()
        if not location:
            break
        timestamp = input("Timestamp (YYYY-MM-DDTHH:MM:SS, leave empty for now): ").strip()
        if not timestamp:
            timestamp = datetime.now().isoformat(timespec="seconds")
        context = input("Context/notes: ").strip()
        try:
            average_speed = float(input("Average speed (km/h, optional): ").strip() or "0")
        except ValueError:
            average_speed = 0
        try:
            length = float(input("Length (meters, optional): ").strip() or "0")
        except ValueError:
            length = 0
        path.add_step(location, timestamp, context, average_speed if average_speed else None, length if length else None)
    return path
