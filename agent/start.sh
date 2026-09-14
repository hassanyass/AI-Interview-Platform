#!/bin/bash
# Deployment target: Railway (2026-09-03), not Render.
#
# The agent used to run here alongside a dummy `python -m http.server`
# purely to satisfy Render's free-tier requirement that a Web Service
# bind to $PORT -- that workaround is gone now that the agent isn't
# deployed to Render at all (see docs/deployment-readiness.md and
# render.yaml's own comment for the full reasoning: Render's free tier
# structurally can't run a real background worker, and the disguise
# workaround was separately confirmed to be a poor fit on measured
# RAM/CPU evidence even before considering its own reliability risk).
#
# Railway needs none of that: confirmed directly against Railway's own
# docs that a background worker requires no $PORT, no public domain, and
# no healthcheck to keep running ("Railway does not monitor the
# healthcheck endpoint after the deployment has gone live").
#
# `start` (not `dev`/`console`/no-subcommand) is the real production
# subcommand -- confirmed 2026-09-02 by reading the installed
# livekit-agents CLI source directly; running with no subcommand prints
# --help and exits without ever starting the worker.
python -m agent.main start
