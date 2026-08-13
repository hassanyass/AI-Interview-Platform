# Data Boundaries

## Runtime State (In-Memory Agent State)
Maintained by the LiveKit Agent during the active call for low-latency reasoning. Lost if the agent process dies (unless restored from DB).
- `current_interview_phase` (e.g., BACKGROUND, CODING)
- `current_question_context`
- `active_guardrails` (e.g., hint_count, time_remaining)
- `conversational_history_buffer`

## Persistent State (PostgreSQL)
Durable data stored in Supabase. The agent flushes relevant runtime data here at checkpoints.
- **User**: Authentication record.
- **CandidateProfile**: Extracted skills/experience.
- **Resume**: PDF storage reference and text.
- **InterviewConfiguration**: 
  - `role`: string
  - `level`: (`junior`, `mid`, `senior`)
  - `language`: (`en` or `ar`)
  - `job_description`: text
  - `duration`: int (minutes)
  - `thinking_time`: int (seconds)
- **InterviewSession**: Links Profile, Config, and final Results.
- **InterviewQuestion**: Technical questions and rubrics.
- **CandidateResponse**: Durable checkpoints of transcript segments.
- **CodeSubmission**: Monaco editor snapshots at specific milestones.
- **InterviewEvaluation / Result**: Final aggregated scores.
