"""CLI entry point for myclaw."""

import argparse
import asyncio

from myclaw.orchestrator import MyclawOrchestrator


def main():
    """Parse CLI arguments and run the myclaw orchestrator."""
    parser = argparse.ArgumentParser(
        prog="myclaw",
        description="A lightweight AI agent orchestrator with pluggable tool support.",
    )
    parser.add_argument(
        "--model",
        help="Model name",
        required=True
    )
    parser.add_argument("--endpoint", help="Model API endpoint", required=True)
    parser.add_argument("--api-key", help="API key for the model endpoint", required=True)
    parser.add_argument(
        "--tools-dir",
        default=None,
        help="Path to a directory of custom tool .py files",
    )
    args = parser.parse_args()

    orchestrator = MyclawOrchestrator(
        model_name=args.model,
        model_endpoint=args.endpoint,
        api_key=args.api_key,
        tools_dir=args.tools_dir,
    )
    asyncio.run(orchestrator.run_async())


if __name__ == "__main__":
    main()
