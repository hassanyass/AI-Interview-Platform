# Technology Stack Recommendation

| Component | Approved Tech | Notes |
| :--- | :--- | :--- |
| **Frontend** | React, TS, Tailwind, shadcn, Monaco | Runs locally for dev. |
| **Backend** | Python, FastAPI | Runs locally for dev. |
| **Realtime** | LiveKit Cloud & LiveKit Agents SDK | Cloud for routing, Agent worker runs locally. |
| **STT** | Deepgram | Lowest latency. Model configurable via ENV. |
| **LLM** | OpenAI | Model configurable via ENV (e.g., GPT-4o). |
| **TTS** | Deepgram | Keep provider abstraction flexible (e.g., evaluate ElevenLabs later). |
| **Database/Auth** | PostgreSQL (Supabase), Supabase Auth | Provides relational data and secure auth. |
| **Storage** | Supabase Storage | For Resume PDFs. |
| **Resume PDF** | PyMuPDF | Fast text extraction. |

## Explicitly Excluded Technologies
To maintain a simple, robust architecture, the following are **NOT** permitted unless a concrete requirement emerges later:
- LangChain, LlamaIndex
- Redis, Kafka, RabbitMQ
- Neo4j, Qdrant, Pinecone, or any Vector Databases
- Additional orchestration frameworks or microservices

## Language Support
The architecture uses a unified pipeline. The target language (`en` or `ar`) is passed as a configuration field to the Agent, dynamically adjusting the LLM system prompt and TTS voice settings.
