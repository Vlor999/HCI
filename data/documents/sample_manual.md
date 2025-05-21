1. Energy Management
    - Monitor and maintain sufficient energy for tasks.
    - Recharge or replace power source when low.
    - Optimize energy consumption during operations.
2. Route Selection & Adaptation
    - Prioritize fastest available routes; avoid blocked roads.
    - Use navigation tools and previous data to determine optimal paths.
    - Adapt routes in real-time using current traffic and road conditions.
3. Weather & Environmental Conditions
    - Detect and adapt to current weather using sensors and past experiences.
    - Avoid risky weather-related situations.
    - Infer seasonality to refine predictions and decision-making.
4. Obstacle Avoidance
    - Identify static and dynamic hazards via sensors (LIDAR, camera).
    - Reroute when obstacles are detected or unavoidable.
5. Environmental Adaptation
    - Adjust behavior based on weather (e.g., rain, snow) and terrain type.
    - Modify speed and movement accordingly.
    - Ensure compatibility with various surfaces and slopes.
6. Location Awareness
    - Recognize previously visited locations and assess:
        - Prior decisions and their outcomes.
        - Environmental changes (e.g., road closures, traffic).
        - Validity of prior choices based on current context.
7. Real-Time Reasoning
    - Use real-time data over historical when discrepancies arise.
    - Update decisions dynamically (e.g., newly opened roads, changed traffic).
8. Decision Prioritization
    - Prioritize safety and efficiency.
    - Resolve data conflicts by favoring real-time inputs.
9. Communication
    - Explain decisions and status clearly to users or systems.
    - Allow for human overrides if needed.
10. Learning & Improvement
    - Continuously learn from past tasks.
    - Analyze data for optimization.
    - Update algorithms for better future performance.
11. Safety Protocols
    - Prioritize human and environmental safety.
    - Comply with regulations and conduct routine maintenance.
12. System Diagnostics
    - Perform regular health checks, log activity, and apply updates.
13. Historical & Provided Data
    - Use previous robot paths, timestamps, and environmental records to inform current decisions.
14. Terrain Features
    - Slope/Gradient: Use LIDAR/IMU to assess steepness and erosion risk.
    - Ground Type: Detect soft, muddy, rocky surfaces to avoid instability.
    - Obstacle Detection: Identify trees, rocks, and debris with LIDAR/camera.
    - Vegetation: Avoid dense or fragile flora to minimize ecological disruption.
15. Environmental Context
    - Predict terrain conditions using weather history and season.
    - Use satellite imagery to avoid wetlands and protected areas.
16. Robot Constraints
    - Account for physical limits: size, weight, slope handling, turning radius.
    - Cross-reference unreliable sensor data (e.g., LIDAR in fog) with IMU/camera/satellite.
17. Path Evaluation
    - Stability: Choose paths with low landslide/erosion risk.
    - Accessibility: Ensure continuity without complex detours.
    - Efficiency: Balance terrain difficulty and distance for energy-saving.
18. Ecological Impact
    - Avoid sensitive habitats and use known trails.
    - Minimize disturbance by favoring low-vegetation or existing paths.
19. Real-Time Stability & Threats
    - Use IMU for tilt detection and terrain monitoring.
    - Detect and respond to moving obstacles like animals or debris.
20. Temporal & Historical Context
    Use time of day and past human/robot trails to avoid high-activity or sensitive zones
