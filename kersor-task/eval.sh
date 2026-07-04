#!/bin/bash
# eval.sh: Wrapper to convert VLIW CYCLES into KerSor's expected time format
cd "$(dirname "$0")/.." || exit 1

# Run the standard evaluation test
OUTPUT=$(python tests/submission_tests.py)

# Extract the cycles count
CYCLES=$(echo "$OUTPUT" | grep "CYCLES:" | awk '{print $2}')

if [ -n "$CYCLES" ]; then
    # Output in a format that KerSor's result-analyzer (Haiku) can easily parse
    echo "[KerSor] Time: $CYCLES ms"
else
    echo "[KerSor] Error: Could not determine cycles."
    echo "[KerSor] Raw output:"
    echo "$OUTPUT"
    echo "[KerSor] Time: 999999 ms"
fi
