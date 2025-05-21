import os
from typer import Option, Typer
from typing import Optional
from src.robotPathExplanation import robotPath
from src.config.constants import MODEL_NAME_ENV, TIMEOUT

app = Typer(help="Human-Robot Communication CLI")


@app.command()  # type: ignore
def explain(
    model: str = Option(MODEL_NAME_ENV, "--model", "-m", help="LLM model to use"),
    timeout: int = Option(TIMEOUT, "--timeout", "-t", help="Timeout for LLM requests"),
    scenario: Optional[int] = Option(None, "--scenario", "-s", help="Scenario index to use"),
    custom: bool = Option(False, "--custom", "-c", help="Create a custom path interactively"),
    addfact: Optional[str] = Option(None, "--addfact", "-f", help="Add a fact before starting"),
    previousConversations: Optional[bool] = Option(
        False, "--prev", "-p", help="(Not yet totally available) Give previous message to the LLM"
    ),
) -> None:

    os.environ["LLM_MODEL"] = model
    os.environ["LLM_TIMEOUT"] = str(timeout)
    if scenario is not None:
        os.environ["SCENARIO_INDEX"] = str(scenario)
    if custom:
        os.environ["USE_CUSTOM_PATH"] = "1"
    if addfact:
        os.environ["CLI_FACT"] = addfact
    if previousConversations:
        os.environ["previousConversations"] = "1"

    robotPath()


if __name__ == "__main__":
    app()
