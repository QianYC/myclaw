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
        default="claude-opus-4.7",
        help="Model name (default: claude-opus-4.7)",
    )
    parser.add_argument("--endpoint", default="http://localhost:4141/", help="Model API endpoint")
    parser.add_argument("--api-key", default="your-api-key", help="API key for the model endpoint")
    args = parser.parse_args()

    orchestrator = MyclawOrchestrator(
        model_name=args.model,
        model_endpoint=args.endpoint,
        api_key=args.api_key,
    )
    asyncio.run(orchestrator.run_async())


if __name__ == "__main__":
    main()
