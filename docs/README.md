# AI Interview Platform - Phase 0 Documentation

This directory contains the Phase 0 foundational architecture and technical decisions for the AI Interview Platform.

## Core Architectural Principle
**"The LLM is the interviewer intelligence; the application controls the interview."**

This principle dictates that the FastAPI application and the state machine handle the lifecycle, timer, phase transitions, and guardrails, while the LLM handles natural conversation, reasoning, and follow-ups within the bounds set by the application.

## Documentation Structure
- `/architecture/`: Context, system design, sequence diagrams, and state machine.
- `/technical/`: Tech stack evaluation, LiveKit details, data model, APIs, and environment.
- `/implementation/`: Future roadmap.
- `PHASE_0_DECISIONS.md`: Final record of approved decisions.
