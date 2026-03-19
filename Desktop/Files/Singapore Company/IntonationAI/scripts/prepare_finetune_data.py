#!/usr/bin/env python3
"""
Phase 2: Prepare fine-tuning data for Vertex AI Gemini from Cheryl Porter and Jodie Langel YouTube content.

Data pipeline:
1. Fetch YouTube transcripts (youtube-transcript-api or manual export)
2. Extract coach-style Q&A pairs from transcripts
3. Convert to JSONL: {"messages": [{"role": "user", "content": "..."}, {"role": "model", "content": "..."}]}
4. Run Vertex AI supervised tuning job

Channels:
- Cheryl Porter Vocal Coach: https://www.youtube.com/c/cherylportervocalcoach
- Jodie Langel Vocal Series: https://www.youtube.com/@jodie_langel

Usage (stub):
    pip install youtube-transcript-api  # when ready
    python scripts/prepare_finetune_data.py --channel-urls URL1 URL2 --output train.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare fine-tuning JSONL from YouTube vocal coach transcripts."
    )
    parser.add_argument(
        "--channel-urls",
        nargs="+",
        help="YouTube channel or video URLs to process",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("train.jsonl"),
        help="Output JSONL file path",
    )
    args = parser.parse_args()

    if not args.channel_urls:
        print("Stub: Add --channel-urls to specify YouTube sources.", file=sys.stderr)
        print("Phase 2 implementation: fetch transcripts, extract Q/A, write JSONL.", file=sys.stderr)
        return 0

    # Placeholder: write empty or sample line
    sample = {
        "messages": [
            {"role": "user", "content": "How do I improve my breath support?"},
            {
                "role": "model",
                "content": "Focus on diaphragmatic breathing. Try straw exercises—blow or sing through a straw to coordinate breath and reduce throat tension.",
            },
        ]
    }
    args.output.write_text(json.dumps(sample) + "\n", encoding="utf-8")
    print(f"Wrote stub to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
