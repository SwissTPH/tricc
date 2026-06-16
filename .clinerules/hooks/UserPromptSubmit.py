#!/usr/bin/env python3
import sys
import json
import subprocess
from pathlib import Path

# Path to your llmlingua-cli
LLMLINGUA_CLI = str(Path.home() / "llmlingua-cli.py")  # or /usr/local/bin/llmlingua

def main():
    # Read input from Cline (JSON via stdin)
    input_data = json.loads(sys.stdin.read())

    original_prompt = input_data.get("prompt", "")
    attachments = input_data.get("attachments", [])

    if not original_prompt.strip():
        print(json.dumps(input_data))  # unchanged
        return

    # Compress with your CLI
    try:
        result = subprocess.run(
            [
                "python", LLMLINGUA_CLI,
                "--target", "800",           # or "--rate", "0.35"
                "--llmlingua2",              # recommended
                original_prompt
            ],
            capture_output=True,
            text=True,
            timeout=15
        )

        if result.returncode == 0:
            compressed = result.stdout.strip()
            # Optional: log compression ratio
            print(f"[LLMLingua Hook] Compressed {len(original_prompt)} → {len(compressed)} chars", file=sys.stderr)
            input_data["prompt"] = compressed
        else:
            print(f"[LLMLingua Hook] Error: {result.stderr}", file=sys.stderr)

    except Exception as e:
        print(f"[LLMLingua Hook] Failed: {e}", file=sys.stderr)

    # Return modified data to Cline
    print(json.dumps(input_data))

if __name__ == "__main__":
    main()