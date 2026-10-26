#!/usr/bin/env bash
# Compatibility wrapper for renamed xvfb-streaming service
exec "$HOME/.hermes/skills/restart-service/scripts/restart-xvfb-streaming.sh" "$@"
