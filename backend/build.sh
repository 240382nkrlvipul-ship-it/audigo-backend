#!/usr/bin/env bash
# Exit immediately if a command exits with a non-zero status
set -e

echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "Ensuring required directories exist..."
mkdir -p data temp

echo "Build completed successfully."
