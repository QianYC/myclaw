from typing import TypedDict
from myclaw.tool_base import ToolBase, tool

class Option(TypedDict):
    label: str
    value: str

class Question(TypedDict):
    question: str
    options: list[Option]
    answer: str = None  # to be filled in by user

@tool
class AskUserQuestionTool(ToolBase):
    name = "ask_user_question"

    def run(self, question: Question) -> Question:
        """
        Use this tool when you need to ask the user questions during execution. This allows you to:
        1. Gather user preferences or requirements
        2. Clarify ambiguous instructions
        3. Get decisions on implementation choices as you work
        4. Offer choices to the user about what direction to take.

        Usage notes:
        - One question per tool call, if you have multiple questions to ask, call this tool multiple times.
        - Users will always be able to select "Other" to provide custom text input.
        - If you recommend a specific option, make that the first option in the list and add "(Recommended)" at the end of the label.

        Plan mode note: In plan mode, use this tool to clarify requirements or choose between approaches BEFORE finalizing your plan. Do NOT use this tool to ask "Is my plan ready?" or "Should I proceed?" - use ExitPlanMode for plan approval.
        IMPORTANT: Do not reference "the plan" in your questions (e.g., "Do you have feedback about the plan?", "Does the plan look good?") because the user cannot see the plan in the UI until you call ExitPlanMode. If you need plan approval, use ExitPlanMode instead.

        Args:
            question: A Question object containing the question text and options for the user to choose from.
        Returns:
            The same Question object with the 'answer' field filled in based on the user's selection.
        """
        print(f"\n[AskUserQuestionTool] {question['question']}")
        for idx, option in enumerate(question['options']):
            print(f"\t{option['label']}. {option['value']}")
        print(f"\tOther (please specify)")
        try:
            choice = int(input("Please select an option by number: ").strip())
            if 1 <= choice <= len(question['options']):
                question['answer'] = question['options'][choice - 1]['value']
            else:
                question['answer'] = input("Please enter your answer: ").strip()
        except ValueError:
            print("Invalid input. Please enter a number corresponding to your choice.")
        return question