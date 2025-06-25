import os
from typer import Option, Typer
from typing import Optional
from src.robotPathExplanation import robotPath
from src.config.constants import MODEL_NAME_ENV, TIMEOUT, LOG_CONVERSATIONS_DIR
from src.evaluation.evaluationRunner import EvaluationRunner

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


@app.command()  # type: ignore
def evaluate(
    log_dir: str = Option(LOG_CONVERSATIONS_DIR, "--log-dir", "-l", help="Directory containing conversation logs"),
    output_dir: str = Option("log/evaluation", "--output-dir", "-o", help="Directory to save evaluation results"),
    no_save: bool = Option(False, "--no-save", help="Don't save results to files"),
) -> None:
    runner = EvaluationRunner(log_dir=log_dir, output_dir=output_dir)
    runner.run_evaluation(save_results=not no_save)


if __name__ == "__main__":
    app()
