import questionary

def ask_question():
    return questionary.text(
        "Ask a question about the path (e.g., 'Is this road a good one to take?')",
        qmark="🤖"
    ).ask() or ""

def print_path(path):
    print("\n📍 Current robot path with context:\n")
    print(path.to_prompt())
    print()

def print_answer(answer):
    print("\n🤖 Robot answer:\n")
    print(answer)

def select_or_edit_question(questions):
    if not questions:
        return None
    choice = questionary.select(
        "Select a previous question to edit (ESC to cancel):",
        choices=questions,
        use_shortcuts=True,
        use_indicator=True,
        qmark="📝"
    ).ask()
    if choice is None:
        print("No question selected. Returning to main menu.")
        return None
    new_question = questionary.text(
        f"Edit your question (was: {choice}):",
        default=choice,
        qmark="✏️"
    ).ask()
    return new_question
