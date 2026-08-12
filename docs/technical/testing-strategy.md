# Testing Strategy

## Frontend
- **Type Checking**: Strict TypeScript compiler checks.
- **Linting**: ESLint + Prettier.
- **Components**: Vitest + React Testing Library for isolated UI logic (e.g., state machine rendering, Monaco editor wrapper).

## Backend
- **Unit Tests**: Pytest for isolated logic (e.g., Resume PDF extraction, State Machine transitions).
- **API Tests**: FastAPI `TestClient` for REST endpoints (mocking DB and LiveKit calls).
- **DB Tests**: Testcontainers or local Postgres to verify Supabase schema queries.

## Agent
- **State Transition Tests**: Unit test the State Machine class independently of LiveKit.
- **Prompt Verification**: Snapshot testing of LLM prompt generation based on varying contexts.
- **Mocked Audio Tests**: Mock the STT/TTS inputs to verify agent interruption/turn-taking logic.

## Integration
- E2E testing of the full pipeline is difficult due to real-time voice. We will rely on manual testing for the LiveKit voice loop, supplemented by integration tests for the REST API -> DB layer.
