.PHONY: run ollama start init venv install format help clean

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

start:
	.venv/bin/python main.py

run: ollama install
	@echo "Waiting for Ollama to be ready..."
	@sleep 2
	$(MAKE) start

init:
	mkdir -p src tests doc data
	touch requirements.txt
	@echo "# Python" > .gitignore
	@echo ".venv/" >> .gitignore
	@echo "__pycache__/" >> .gitignore
	@echo "*.pyc" >> .gitignore
	@echo "ollama.log" >> .gitignore
	@echo "data/" >> .gitignore
	@echo "Structure initialisée."

help:
	@echo "Available targets:"
	@echo "  venv       - Create a Python virtual environment if it doesn't exist."
	@echo "  install    - Install dependencies from requirements.txt."
	@echo "  format     - Format the code in the src/ directory using Black."
	@echo "  ollama     - Start the Ollama server in the background if not already running."
	@echo "  start      - Run the main Python script (robot_path_explanation.py)."
	@echo "  run        - Install dependencies, start Ollama, and run the main script."
	@echo "  init       - Initialize the project structure and create a .gitignore file."
	@echo "  clean      - Remove the virtual environment, cache files, and logs."

clean:
	rm -rf .venv __pycache__ src/__pycache__ tests/__pycache__ ollama.log
