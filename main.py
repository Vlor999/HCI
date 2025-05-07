import sys
from src.cli import app
from src.robotPathExplanation import robotPath


def main() -> None:
    robotPath()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        app(prog_name="python main.py")
    else:
        robotPath()
