from src.core.path import Path, PathStep
from datetime import datetime


def create_custom_path() -> Path:
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

        print("Terrain features:")
        slope = input("  Slope (e.g., flat, moderate, steep): ").strip()
        ground_type = input("  Ground type (e.g., muddy, rocky, sandy): ").strip()
        obstacle_density = input("  Obstacle density (e.g., low, medium, high): ").strip()
        vegetation = input("  Vegetation (e.g., sparse, dense): ").strip()
        terrain_features = {
            "slope": slope,
            "ground_type": ground_type,
            "obstacle_density": obstacle_density,
            "vegetation": vegetation,
        }

        energy_consumption = input("Energy consumption (e.g., low, medium, high): ").strip()
        ecological_impact = input("Ecological impact (e.g., low, medium, high): ").strip()
        seasonal_info = input("Seasonal info (e.g., winter conditions): ").strip()

        step = PathStep(
            location=location,
            timestamp=timestamp,
            context=context,
            average_speed=average_speed if average_speed else None,
            length=length if length else None,
            terrain_features=terrain_features,
            energy_consumption=energy_consumption,
            ecological_impact=ecological_impact,
            seasonal_info=seasonal_info,
        )
        path.add_step(step)
    return path
