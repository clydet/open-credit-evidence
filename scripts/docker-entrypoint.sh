#!/bin/bash
# Entrypoint for Docker: passes all args to run_wed_gate.py
# Default (no args) uses CMD from Dockerfile/Compose, which is --stub
exec python scripts/run_wed_gate.py "$@"
