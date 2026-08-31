# TTS Provider Switching — Azure ↔ Groq

Not a numbered phase — a reference note. Read this before touching TTS
provider config, and update it if the switch mechanism ever changes shape.

## TL;DR

The active TTS provider is a **single environment variable**, not a code
change:

```
TTS_PROVIDER=groq    # current default (as of 2026-08-31) — multi-key rotation makes the quota problem a non-issue
TTS_PROVIDER=azure   # still fully wired, was the default 2026-08-27 through 2026-08-31
```

Set it in `.env` (root — authoritative, loaded first with `override=True`
by `agent/main.py`'s `_load_env()`), then **restart the agent worker**
(`python -m agent.main dev`). Env vars are only read at process startup /
session load — there is no hot-reload for this. No file other than `.env`
needs to change to flip providers.

## Why Groq is viable again (it wasn't, briefly)

Groq's free-tier TTS quota is a hard **3,600 tokens/day (TPD)** ceiling
*per key, per model* — confirmed live against the real account on
2026-08-27 (see `docs/CURRENT_DECISIONS.md`): a single day of internal
testing exhausted it outright (3,536/3,600 used), which is why this
project ran on Azure for a few days. That's still true of any ONE key —
what changed is **multi-key rotation** (2026-08-31, see below): the
project now runs on up to 7 real Groq keys provisioned for prototype user
testing, and the agent rotates to the next one automatically, immediately,
the instant the current one hits its daily ceiling. A different key has
its own independent quota, so this isn't "wait it out" — it's a real fix
for the actual failure mode. Azure Speech remains fully wired as the
zero-quota-risk alternative if this project ever needs to drop Groq
entirely again.

## Groq multi-key rotation (2026-08-31)

**File:** `agent/agent/interview/groq_key_rotator.py`.

- Reads `GROQ_API_KEY_1` .. `GROQ_API_KEY_7` (up to 20 supported) from
  `.env`, in order, skipping any unset/empty ones. Falls back to the
  single legacy `GROQ_API_KEY` (already used by STT/LLM) as the only key
  if none of the numbered ones are configured — fully backward compatible
  with a single-key setup, rotation just never has anywhere to go.
- **English and Arabic get independent rotators** — separate Groq models
  (`canopylabs/orpheus-v1-english` / `canopylabs/orpheus-arabic-saudi`),
  separate quotas, both drawing from the same pool of 7 keys but tracking
  their own position in it independently.
- On a 429, rotation is **immediate — no backoff delay**. A different
  key's quota doesn't become more available by waiting, unlike the
  escalating-backoff logic further below (which still applies to Azure,
  or to Groq running on a single unrotatable key — see "How the pieces
  fit together").
- State (which key each rotator is currently on) is **disk-persisted**
  per-language (`agent/.groq_key_state_en.json` /
  `agent/.groq_key_state_ar.json`, gitignored) — not just in-memory,
  because each candidate session runs in its own worker subprocess
  (confirmed live), so a purely in-process counter would reset to key 1
  for every fresh session and re-waste a guaranteed 429 rediscovering
  that key 1 is already exhausted for the day. A new session picks up
  exactly where the last one left off.
- Resets back to key 1 automatically at UTC day rollover (checked on
  every rotator construction, i.e. every new session) — yesterday's
  exhausted key 1 has a fresh quota today, no reason to stay parked on
  key 7 forever.
- The frontend gets real, live signal for this — see "Frontend: the
  `switching_key` status" below — not silence while it happens.

**Setup:** add your 7 real keys to root `.env`'s `GROQ_API_KEY_1`
through `GROQ_API_KEY_7` placeholders (also mirrored, empty, in
`.env.example` and `agent/.env`) — do not paste them in chat.

## Option A — Groq (current default, multi-key rotation)

**Required env vars** (root `.env`):
```
TTS_PROVIDER=groq
GROQ_API_KEY_1=<real key 1>          # through GROQ_API_KEY_7 — see the
GROQ_API_KEY_2=<real key 2>          # multi-key rotation section above.
...                                    # Not required — falls back to the
GROQ_API_KEY_7=<real key 7>          # single GROQ_API_KEY below if unset.
GROQ_API_KEY=<real key>                                   # already set — shared with STT/LLM
GROQ_TTS_ENGLISH_MODEL=canopylabs/orpheus-v1-english       # optional, already the default
GROQ_TTS_ARABIC_MODEL=canopylabs/orpheus-arabic-saudi      # optional, already the default
GROQ_TTS_ENGLISH_VOICE=troy                                # optional, already the default
```
(The Arabic voice, `abdullah`, is currently hardcoded rather than
env-driven — predates this switch, not changed as part of this work.)

**Known limitation:** the 3,600 TPD-per-key ceiling still applies to each
INDIVIDUAL key — rotation works around it by having several, it doesn't
raise any one key's own limit. If every configured key is exhausted on
the same day (unlikely with 7, but possible under heavy testing), the
agent falls back to the client-side Web Speech API for that turn (see
`docs/tts-provider-switching.md`'s Azure section era work — same
`gave_up` broadcast either way, provider-agnostic).

## Option B — Azure Speech (zero quota risk, no rotation needed)

**Required env vars** (root `.env`):
```
TTS_PROVIDER=azure
AZURE_SPEECH_KEY=<real key>
AZURE_SPEECH_REGION=<real region, e.g. eastus>
AZURE_TTS_ENGLISH_VOICE=en-US-AvaNeural     # optional, this is already the default
AZURE_TTS_ARABIC_VOICE=ar-SA-HamedNeural    # optional, this is already the default
```

Voices chosen (see `agent/agent/main.py`'s inline comments for the full
reasoning):
- **English:** `en-US-AvaNeural` — one of Azure's newer voices tuned for
  conversational/casual dialogue, not formal narration; a stable GA voice
  (not the newer Dragon-HD-preview tier, which isn't guaranteed available
  on every region/subscription).
- **Arabic:** `ar-SA-HamedNeural` — one of exactly two ar-SA neural voices
  Azure offers (the other is Zariyah/female); Hamed picked for consistency
  with `InterviewerCharacter.tsx`'s existing male-presenting avatar. See
  `docs/CURRENT_DECISIONS.md`/the live voice-comparison audio files
  (2026-08-31) if a different Arabic voice is ever picked instead.

**Package:** `livekit-plugins-azure` (already in `agent/requirements.txt`).

The TTS retry-with-backoff, the `tts_status` broadcast, the browser Web
Speech API fallback, and the fixed-message disk cache
(`agent/agent/interview/tts_cache.py`) all still work regardless of which
provider is active — none of that (or the key-rotation machinery) is
Groq-specific in a way that breaks Azure; rotation is simply a no-op path
for Azure (`getattr(tts_plugin, "key_rotator", None)` is `None`), falling
through to the plain escalating-backoff retry instead.

## Frontend: the `switching_key` status

`TtsRetryOverlay.tsx` renders a distinct visual state for a Groq key
rotation in flight — `tts_status.status === "switching_key"` — separate
from the older `"retrying"` state (Azure's/single-key Groq's escalating
backoff) and `"gave_up"` (every option exhausted, client-side fallback
speaking now). Deliberately its own copy, not reused "reconnecting"
wording — rotation is near-instant, framing it as a slow reconnect would
be misleading. `attempt`/`max` on this status are the 1-based key
position and total key count (e.g. "switching to key 2 of 7"), not a
retry counter. See `frontend/src/types/realtime.ts`'s `TtsStatusPayload`
and the locale strings under `workspace.ttsSwitchingKey*` (en/ar).

## How to verify which provider — and which key — is actually active

After restarting the agent worker, check its log for either session
startup or an actual candidate session load:
```
TTS provider: azure    # or: TTS provider: groq
TTS voice: en-US-AvaNeural    # or whichever voice/model is active
Groq key rotator: key 1/7     # Groq only — 1-based position / total configured keys
```
These lines are logged unconditionally on every session load — grep for
`"TTS provider:"` or `"GROQ-KEY-ROTATOR"` in `agent_run.log` (or wherever
you're piping the worker's stdout) to confirm. A rotation event during a
live session logs `[GROQ-KEY-ROTATOR:<en|ar>] Rotated to key N/M`.

## Where the actual switch logic lives

`agent/agent/main.py`, inside `entrypoint()`, right after `# ─── Initialize
Voice Plugins ───`. One `tts_provider = os.getenv("TTS_PROVIDER",
"azure").lower()` read, then an `if tts_provider == "azure": ... else:
...` branch inside each of the `language == "ar"` / else (English) cases —
four total instantiation sites (Azure EN, Groq EN, Azure AR, Groq AR), each
setting `tts_plugin.provider_name` / `tts_plugin.model_name` for logging.
Nothing outside this block (voice_adapter.py's playback pipeline, RT-B0's
metrics listeners, RT-B1's interruption/`clear_queue()` fix, the retry/
cache/fallback machinery) needs to know or care which provider is active —
confirmed by direct source inspection that both providers' plugins share
the same `livekit.agents.tts.TTS` / `ChunkedStream` / `AudioEmitter` base
classes Groq's plugin already used.

## Adding a third provider later

If a third TTS provider is ever added, follow the same shape: one more
`elif tts_provider == "<name>":` branch per language inside the existing
`if language == "ar": ... else: ...` blocks, reading that provider's own
env vars with sensible defaults, setting `provider_name`/`model_name` the
same way. No other file should need to change for the swap itself — only
for genuinely new work (e.g., picking that provider's own voice IDs).
