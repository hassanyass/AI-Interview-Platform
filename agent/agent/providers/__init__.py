"""Provider construction for the agent worker (LLM, STT, TTS, VAD), driven by
agent.config.AgentSettings. Extracted from main.entrypoint in H1-C
(docs/production-hardening-plan.md) so the entrypoint reads as lifecycle, not
vendor wiring, and so the VAD model is loaded once per process (prewarm)."""
