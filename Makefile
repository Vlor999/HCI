.PHONY: run ollama start init venv install format help clean test stop-ollama

venv:
	@test -d .venv || python3 -m venv .venv

install: venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements.txt

format:
	.venv/bin/black src/

ollama:
	@echo "Starting Ollama server in the background (if not already running)..."
	@pgrep -f "ollama serve" > /dev/null || nohup ollama serve > ollama.log 2>&1 &

stop-ollama:
	@echo "Stopping all Ollama server processes..."
	@pkill -f "ollama serve" || true

start:
	.venv/bin/python main.py

run: ollama install
	@echo "Waiting for Ollama to be ready..."
	@sleep 2
	$(MAKE) start

test:
	.venv/bin/python -m unittest discover -s tests

coverage:
	.venv/bin/pip install coverage
	.venv/bin/coverage run -m unittest discover -s tests
	.venv/bin/coverage report -m
	.venv/bin/coverage html
	@echo ""
	@echo "HTML coverage report generated at htmlcov/index.html"
	@echo "To view it, open the file in your browser:"
	@echo " * open htmlcov/index.html"
	@echo "Or on Linux:"
	@echo " * xdg-open htmlcov/index.html"

mypy:
	.venv/bin/pip install mypy types-requests
	.venv/bin/mypy src/

init:
	mkdir -p src tests doc data log
	touch requirements.txt
	@touch src/__init__.py
	@echo "# Python" > .gitignore
	@echo ".venv/" >> .gitignore
	@echo "__pycache__/" >> .gitignore
	@echo "*.pyc" >> .gitignore
	@echo "ollama.log" >> .gitignore
	@echo "data/" >> .gitignore
	@echo "log/" >> .gitignore
	@echo "Structure initialisée."

help:
	@echo "Available targets:"
	@echo "  venv       - Create a Python virtual environment if it doesn't exist."
	@echo "  install    - Install dependencies from requirements.txt."
	@echo "  format     - Format the code in the src/ directory using Black."
	@echo "  ollama     - Start the Ollama server in the background if not already running."
	@echo "  stop-ollama - Stop all running Ollama server processes."
	@echo "  start      - Run the main Python script (robot_path_explanation.py)."
	@echo "  run        - Install dependencies, start Ollama, and run the main script."
	@echo "  test       - Run all unittests in the tests/ directory."
	@echo "  coverage   - Run coverage analysis on the tests."
	@echo "  mypy       - Run mypy static type checks on the src/ directory."
	@echo "  init       - Initialize the project structure and create a .gitignore file."
	@echo "  clean      - Remove the virtual environment, cache files, logs, and output markdown in log/."
	@echo ""
	@echo "The final output markdown file is saved in the log/ directory."

clean:
	rm -rf .venv __pycache__ src/__pycache__ tests/__pycache__ ollama.log log/
