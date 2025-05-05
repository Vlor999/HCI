def ask_question():
    return input("Ask a question about the path (e.g., 'Is this road a good one to take?'): ")

def print_path(path):
    print("Current robot path with context:")
    print(path.to_prompt())
    print()

def print_answer(answer):
    print("\nRobot answer:\n")
    print(answer)
