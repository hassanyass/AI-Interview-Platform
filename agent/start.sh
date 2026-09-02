#!/bin/bash
# Start a dummy HTTP server on the port Render provides (default 8000)
# This satisfies Render's requirement for Web Services to bind to a port,
# allowing the agent to run on the 100% free tier.
python -m http.server ${PORT:-8000} &

# Run the LiveKit agent
python -m agent.main
