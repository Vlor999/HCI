import typer
from typing import Optional
from src.robotPathExplanation import robotPath
from src.config.constants import MODEL_NAME_ENV, TIMEOUT

app = typer.Typer(help="Human-Robot Communication CLI")


@app.command()
def explain(
    model: str = typer.Option(MODEL_NAME_ENV, "--model", "-m", help="LLM model to use"),
    timeout: int = typer.Option(
        TIMEOUT, "--timeout", "-t", help="Timeout for LLM requests"
    ),
    scenario: Optional[int] = typer.Option(
        None, "--scenario", "-s", help="Scenario index to use"
    ),
    custom: bool = typer.Option(
        False, "--custom", "-c", help="Create a custom path interactively"
    ),
    addfact: Optional[str] = typer.Option(
        None, "--addfact", "-f", help="Add a fact before starting"
    ),
):
    """
    Start the robot path explanation session with optional CLI overrides.
    """
    import os

    # Pass CLI options to robotPath via environment variables or direct arguments
    os.environ["LLM_MODEL"] = model
    os.environ["LLM_TIMEOUT"] = str(timeout)
    if scenario is not None:
        os.environ["SCENARIO_INDEX"] = str(scenario)
    if custom:
        os.environ["USE_CUSTOM_PATH"] = "1"
    if addfact:
        os.environ["CLI_FACT"] = addfact

    robotPath()


if __name__ == "__main__":
    app()
