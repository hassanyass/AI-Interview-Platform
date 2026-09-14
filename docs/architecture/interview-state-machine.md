# Interview State Machine

To provide **structural control without making the conversation rigid**, the state machine separates macro-level phases from micro-level conversational actions. 

The application controls the **Phases**, while the LLM has flexibility over the **Actions** within the permitted phase.

## A. Interview Phases (Application Controlled)
The controller strictly enforces these transitions, maximum duration, topic boundaries, and question progression:
1. **WELCOME**: Small talk, sound check, introduction.
2. **BACKGROUND**: Discussing candidate's resume/experience.
3. **TECHNICAL**: Introducing the coding challenge, reading the question, thinking time, and approach discussion.
4. **CODING**: Candidate writes code in Monaco. AI handles clarifications and graduated hints.
5. **CLOSING**: AI concludes the interview and wraps up.

## B. Conversational Actions (LLM Controlled)
Within any given Phase, the LLM utilizes these conversational actions dynamically:
- **ASK**: Pose a question to the candidate.
- **LISTEN**: Wait for the candidate to speak or finish.
- **FOLLOW_UP**: Ask deeper questions based on the previous answer.
- **CLARIFY**: Clarify misunderstandings or repeat instructions.
- **HINT**: Provide a graduated hint (if permitted by application hint policy).
- **ACKNOWLEDGE**: Confirm understanding of the candidate's input.
- **TRANSITION**: Signal readiness to move to the next topic/phase (triggers application controller).
- **EVALUATE**: Assess reasoning or code implementation internally.

## Application Controller Guardrails
The Agent's controller enforces:
- Allowed interview phases (no jumping from WELCOME straight to CLOSING unless user terminates).
- Maximum duration (forces transition to CLOSING when time expires).
- Hint policy (LLM cannot give the full solution).
- Error recovery (fallback to predefined prompts if STT/LLM fails).
- User termination (graceful exit if user clicks "End Interview").
