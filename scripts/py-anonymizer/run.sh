#!/bin/bash
# py-anonymizer-semann-gemtex launcher for Unix/Linux/macOS

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ ! -f "$SCRIPT_DIR/main.py" ]; then
    echo "Error: main.py not found in $SCRIPT_DIR"
    exit 1
fi

# Try python3 first, then python
if command -v python3 &> /dev/null; then
    PYTHON=python3
elif command -v python &> /dev/null; then
    PYTHON=python
else
    echo "Error: Python not found. Please install Python 3.7+ and add it to PATH."
    exit 1
fi

$PYTHON "$SCRIPT_DIR/main.py" "$@"
