#!/bin/bash
# Start a dummy HTTP server on the port Render provides (default 8000)
# This satisfies Render's requirement for Web Services to bind to a port,
# allowing the agent to run on the 100% free tier.
#
# Deployment-readiness audit (2026-09-02, docs/deployment-readiness.md):
# this free-tier-web-service disguise is now confirmed, separately, to be
# a poor fit regardless of this file's own bugs -- see that doc's
# "Combined single-container" follow-up research for the real RAM/CPU
# evidence. Left in place (not reverted) since a hosting decision hasn't
# been made yet; the bug below is real and worth fixing independent of
# which host is ultimately chosen.
python -m http.server ${PORT:-8000} &

# Run the LiveKit agent
# Bug fix (2026-09-02): `python -m agent.main` with no subcommand does not
# start the worker -- confirmed by reading the installed livekit-agents
# CLI source directly (site-packages/livekit/agents/cli/_legacy.py): with
# no subcommand, it prints --help and exits immediately. `start` is the
# real production subcommand (distinct from `dev`/`console`/
# `download-files`). Before this fix, the container would launch, the
# dummy HTTP server above would satisfy Render's health check, and the
# agent itself would silently exit almost immediately -- going offline
# with no crash or error surfaced anywhere.
python -m agent.main start
