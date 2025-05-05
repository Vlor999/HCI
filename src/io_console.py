import questionary

def ask_question():
    out = "Ask a question about the path (e.g., 'Is this road a good one to take?') "
    return questionary.text(
            out,
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
        "Select a previous question to edit or press ESC to cancel:",
        choices=questions
    ).ask()
    if choice:
        new_question = questionary.text(
            f"Edit your question (was: {choice}):",
            default=choice
        ).ask()
        return new_question
    return None
