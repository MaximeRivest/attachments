#!/usr/bin/env python3
"""
CLI entry point for the Attachments tool.

This script accepts one or more file or directory paths and an optional DSL
string to control processing. It prints the aggregated text output to stdout.
"""

import sys
import argparse
from attachments import Attachments, set_verbose


def main():
    parser = argparse.ArgumentParser(
        description="Convert files or directories into LLM-ready text via Attachments DSL."
    )
    parser.add_argument(
        "paths",
        nargs="+",
        help="One or more file or directory paths to process."
    )
    parser.add_argument(
        "-d", "--dsl",
        default="",
        help="Optional DSL fragment to append to each path, e.g. \"[files:true][mode:report]\""
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress verbose logging (default is verbose)."
    )

    args = parser.parse_args()

    # Configure logging verbosity
    set_verbose(not args.quiet)

    # Build input strings with DSL if provided
    inputs = []
    if args.dsl:
        for p in args.paths:
            inputs.append(f"{p}{args.dsl}")
    else:
        inputs = args.paths

    try:
        # Process attachments and print the combined text
        ctx = Attachments(*inputs)
        output = str(ctx)
        if output:
            print(output)
    except Exception as e:
        print(f"Error running Attachments CLI: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
