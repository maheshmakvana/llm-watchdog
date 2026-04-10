"""CLI entry point for promptwatch."""
from __future__ import annotations

import argparse
import json
import sys


def main() -> None:
    """promptwatch CLI — monitor LLM responses from the command line."""
    parser = argparse.ArgumentParser(
        prog="promptwatch",
        description="Detect silent failures in LLM responses",
    )
    parser.add_argument("--prompt", required=True, help="The prompt text")
    parser.add_argument("--response", required=True, help="The LLM response text")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    from .watcher import PromptWatcher
    watcher = PromptWatcher()
    result = watcher.watch(args.prompt, args.response)

    if args.json:
        print(json.dumps(result.to_dict(), indent=2, default=str))
    else:
        status = "PASS" if result.passed else "FAIL"
        print(f"[{status}] Risk: {result.overall_risk.value} | Score: {result.overall_score:.3f}")
        for d in result.detections:
            if d.detected:
                print(f"  ⚠  {d.failure_type.value}: score={d.score:.3f} risk={d.risk_level.value}")


if __name__ == "__main__":
    main()
