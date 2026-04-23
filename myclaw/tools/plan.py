"""Plan-mode tools: enter and exit the agent's planning mode."""

from myclaw.tool_base import ToolBase, tool
from myclaw.orchestrator import Mode


@tool
class EnterPlanModeTool(ToolBase):
    """Switch the agent into planning mode.

    Planning mode uses a different system prompt and may have access to a
    different set of tools.
    """

    name = "enter_planning_mode"

    # pylint: disable=arguments-differ
    def run(self) -> str:
        """
        Use this tool proactively when you're about to start a non-trivial task.
        This tool transitions the agent into the plan mode in which the agent
        will first create a step-by-step plan instead of directly executing
        actions.

        When to Use This Tool

        Prefer using EnterPlanMode for implementation tasks unless they're
        simple. Use it when ANY of these conditions apply:

        1. Software engineering task: User is asking for making a code change,
           choosing architectual design, or implementing a feature. These
           tasks often require careful planning and consideration of
           trade-offs.
            - Example: "Implement a new feature that allows users to save
              their preferences.
            - Example: "Refactor the existing codebase to improve
              maintainability and scalability."
        2. Unclear Requirements: You need to explore before understanding the
           full scope
            - Example: "Make the app faster" - need to profile and identify
              bottlenecks
            - Example: "Fix the bug in checkout" - need to investigate root
              cause
        3. Complex multi-step tasks: The task is inherently complex and likely
           requires multiple steps to complete, even if the user has given
           specific instructions.
            - Example: "I'd like to travel to somewhere." - you need to ask
              follow-up questions to understand preferences and constraints,
              then help plan every aspect of the trip e.g. transportation,
              hotels, activities, etc.
            - Example: "I want to start a business." - you need to help them
              brainstorm business ideas, then create a plan for market
              research, funding, product development, etc.

        When NOT to Use This Tool

        Only skip EnterPlanMode for simple tasks:
            - Single-line or few-line fixes (typos, obvious bugs, small
              tweaks)
            - Adding a single function with clear requirements
            - Tasks where the user has given very specific, detailed
              instructions
            - Pure research/exploration tasks (use the Agent tool with explore
              agent instead)

        Returns:
            Confirmation message that the agent has entered planning mode.
        """
        self.orchestrator.mode = Mode.PLANNING
        return "Agent has entered PLANNING mode."


@tool
class ExitPlanModeTool(ToolBase):
    """Switch the agent back to default mode from planning mode."""

    name = "exit_planning_mode"

    # pylint: disable=arguments-differ
    def run(self, plan: str) -> str:
        """
        Use this tool when the agent has completed the planning phase and is
        ready to execute the plan. This tool asks for user confirmation
        before switching back to default mode, giving the user a chance to
        review the plan and make any necessary adjustments before execution.

        Args:
            plan: The step-by-step plan created by the agent in planning
                mode. This is provided as context for the user to review
                before confirming exit from planning mode.
        Returns:
            Confirmation message that the agent has exited planning mode.
        """
        print(f"\n[PlanMode] Here's the plan for you:\n{plan}\n")
        confirmation = input(
            "[PlanMode] Do you approve this plan? (y/N/revision): "
        ).strip().lower()
        if confirmation == "y":
            self.orchestrator.mode = Mode.DEFAULT
            return "User has approved the plan. Continue to plan execution."
        if confirmation.startswith("r"):
            revision = input(
                "[PlanMode] Please provide your revisions to the plan: "
            )
            return (
                f"User suggested revisions: {revision}. Please update the "
                "plan accordingly and then call this tool again to confirm "
                "the updated plan."
            )
        self.orchestrator.mode = Mode.DEFAULT
        return "Plan not approved. Stop further processing."
