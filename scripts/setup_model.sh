#!/bin/bash
# Usage: ./scripts/setup_model.sh <model_name>
set -e

MODEL="$1"
if [ -z "$MODEL" ]; then
  echo "Usage: ./scripts/setup_model.sh <model_name>"
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIR="$ROOT/models/$MODEL"

if [ ! -d "$DIR" ]; then
  echo "Error: $DIR does not exist."
  echo "Copy the template first:"
  echo "  cp -r models/_template models/$MODEL"
  exit 1
fi

echo "Setting up venv for '$MODEL'..."
python3 -m venv "$DIR/.venv"
"$DIR/.venv/bin/pip" install --quiet --upgrade pip
"$DIR/.venv/bin/pip" install -r "$DIR/requirements.txt"
echo "Done! Restart the backend to pick up the new model."
