# HCI Robot Path Explanation Project

This project demonstrates how to use a Large Language Model (LLM) to explain and reason about robot navigation paths, integrating environmental context and user questions.

## Prerequisites

- **Python 3.8+** (recommended: 3.11)
- **[Ollama](https://ollama.com/)** (local LLM server)
- **llama3.2** model (or another compatible model installed in Ollama)
- **make** (optional, for easier automation)

## Setup Instructions

1. **Clone the repository** (if not already done):

   ```sh
   git clone git@github.com:Vlor999/HCI.git
   cd HCI
   ```

2. **Install Ollama and the LLM model:**

   - [Download and install Ollama](https://ollama.com/download)
   - Start Ollama (if not already running):

     ```sh
     ollama serve
     ```

   - Pull the model (e.g., llama3.2):

     ```sh
     ollama pull llama3.2
     ```

3. **Initialize the project structure and install Python dependencies:**

   ```sh
   make init
   make install
   ```

   This will:
   - Create necessary folders (`src/`, `tests/`, `data/`, `log/`, etc.)
   - Install Python dependencies in a virtual environment

4. **(Optional) Format the code:**

   ```sh
   make format
   ```

5. **Run the project:**

   ```sh
   make run
   ```

   or manually:

   ```sh
   .venv/bin/python main.py
   ```

6. **Run the tests:**

   ```sh
   make test
   ```

## Usage

- When running, the program will display the current robot path and context.
- You can ask multiple questions about the path and its conditions.
- Type `exit` or `quit` to end the session.
- After exiting, a Markdown log of the conversation will be saved in the `log/` directory.

## Project Structure

```
src/           # Source code (robotPathExplanation.py, path.py, io_console.py, etc.)
tests/         # Unit tests
data/          # Example path data (JSON)
log/           # Conversation logs (Markdown)
doc/           # Documentation
Makefile       # Automation commands
requirements.txt
```

## Notes

- You can edit `data/paths.json` to add or modify path scenarios.
- The LLM model name can be changed in the code if you use a different one.
- The `.gitignore` file ensures that data, logs, and virtual environments are not committed.

## Troubleshooting

- **Ollama not running:** Make sure `ollama serve` is active and the model is pulled.
- **Port conflicts:** Only one Ollama server should run at a time on port 11434.
- **Python errors:** Ensure you are using the virtual environment (`.venv`).

---

For more details, see the documentation in `doc/` or the comments in the source files.

---

## License

This project is licensed under the [MIT License](LICENSE).
