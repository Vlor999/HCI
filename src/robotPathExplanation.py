import requests
from datetime import datetime

def robotPath():
    # Define the robot's path
    robot_path = [
        {"location": "A", "timestamp": datetime(2023, 1, 1, 10, 0)},
        {"location": "B", "timestamp": datetime(2023, 1, 1, 10, 30)},
        {"location": "C", "timestamp": datetime(2023, 1, 1, 11, 0)},
    ]

    # Create a prompt for the robot to explain its path
    prompt = (
        "Your focus should be on the robot's ability to evaluate its past decisions, "
        "such as revisiting a location. For instance, the robot might reason: "
        "\"I recognize this area—I visited it on [date/time] and made a specific decision.\" "
        "If the environment has changed, the robot should adapt its reasoning to account for these changes, "
        "rather than relying solely on previous decisions."
    )

    # Send the prompt to the explanation API
    response = requests.post(
        "http://localhost:8000/explain",
        json={"prompt": prompt, "path": robot_path}
    )
    explanation = response.json().get("response", "")

    print("Robot explanation:\n")
    print(explanation)

