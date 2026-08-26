# AGENTS.md — Path2Hire B2C→B2B Transition

Antigravity: read this file in full before proposing any plan or code change. It is authoritative over your own inference about this codebase. If something here conflicts with what you observe in the code, STOP and ask — do not silently resolve the conflict.

## 0. Reference documents (read these, don't paraphrase from memory)
- `docs/path2hire-transition-plan.md` — the full phased plan. Work ONLY within the phase I name in my prompt.
- `docs/CURRENT_DECISIONS.md` — confirmed product decisions. Anything not listed there as decided is UNRESOLVED — you may not assume an answer to it.

## 1. Naming — do not deviate
Use these exact entity names everywhere. Do not rename, abbreviate, or introduce synonyms:
`Job`, `InterviewDefinition`, `InterviewSection`, `InterviewQuestion`, `CandidateInterviewSession`, `Candidate`, `Evaluation`, `Score`.
Legacy names still in the current codebase: `InterviewConfiguration`, `InterviewSession` — these stay until the plan's Phase 10 explicitly retires them. Do not rename them early "for consistency."

## 2. Frozen contracts — never touch without explicit sign-off
- `agent/app/interview/controller.py` and anything under `/internal/*` (the LiveKit Agent Worker's API contract). Frozen by default — modifications require an active, approved sub-phase plan that explicitly scopes touching them (originally Phase 7's legacy-format adapter; the same rule now governs any later phase/sub-phase, e.g. Phase 9, that needs to touch it — it is not limited to Phase 7 anymore).
- `InterviewerCharacter.tsx` — reusable as-is, do not refactor.

## 3. Migration rules
- All database migrations are additive-only unless the phase explicitly says "drop" or "make mandatory." New tables and nullable foreign keys — never a destructive rewrite of an existing table in the same change that adds a feature.
- Never let `InterviewConfiguration` stop working for existing sessions until Phase 10.

## 4. Required workflow for every task (Explore → Plan → Execute)
1. **Explore first.** Open and quote the actual current contents of every file you're about to touch. Do not describe a file's contents from a prior summary — re-read it.
2. **Plan before code.** Output a short implementation plan: files touched, models/migrations added or changed, and anything from `CURRENT_DECISIONS.md` this depends on. Wait for my go-ahead on anything touching a "frozen contract" file above.
3. **Execute.** Apply the change.
4. **Verify.** Run the test suite / relevant test command and show me the output before declaring the task done. If no test covers the change, write one first.

## 5. Unresolved items — do not decide these yourself
If a task depends on an item still marked unresolved in `CURRENT_DECISIONS.md` (e.g. anonymous vs. authenticated candidates, email provider, code sandbox scope), stop and flag it to me by name instead of picking a default.

## 6. Scope discipline
Only do what the current prompt/phase asks. If you notice something adjacent that seems worth fixing or improving, tell me — don't fix it inline as a "drive-by" change in the same diff.

## 7. Test file discipline
Never delete, move, or overwrite any existing test file without first stopping and asking for explicit confirmation — even if the file appears unrelated to the current task, unused, or like scratch/duplicate code. File-name similarity to the current task's terminology (e.g. matching phase numbers from a different numbering scheme) is not sufficient grounds to assume a file is safe to remove.
