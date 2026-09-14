import { Loader2, Sparkles } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { TtsStatusPayload } from "../../types/realtime";

/**
 * TtsRetryOverlay — a blurred backdrop shown over the live interview content
 * while the agent's own voice is either mid-backoff-retry, mid-key-rotation,
 * or has given up (see voice_adapter.py's _broadcast_tts_status). Lets the
 * candidate know something is actively being handled server-side, rather
 * than silence that looks indistinguishable from the agent simply never
 * responding.
 *
 * Three distinct visual states, not one generic "having trouble" message:
 * - "retrying": the old escalating-backoff path (Azure, or Groq running on
 *   a single legacy key with no rotation configured) — a real wait is
 *   happening, framed as "reconnecting".
 * - "switching_key" (2026-08-27, follow-up): Groq multi-key rotation — near
 *   -instant, no real wait, framed as its own "switching voices" moment
 *   rather than reusing "reconnecting" copy that would imply a slow
 *   process it isn't.
 * - "gave_up": every option exhausted — the browser's own Web Speech API
 *   fallback is now speaking this line instead.
 *
 * Deliberately positioned as an absolutely-positioned child of the content
 * wrapper BELOW the header (not a page-wide fixed overlay) — the header
 * (logo, phase label, timer, End Session) is a sibling outside this
 * wrapper, so it stays fully visible and clickable above the blur without
 * any z-index/height math. The candidate can always end the session even
 * while this is showing.
 */
interface TtsRetryOverlayProps {
  ttsStatus: TtsStatusPayload | null;
}

export function TtsRetryOverlay({ ttsStatus }: TtsRetryOverlayProps) {
  const { t } = useTranslation();

  if (!ttsStatus || ttsStatus.status === "ok") return null;

  const { status } = ttsStatus;
  const isGaveUp = status === "gave_up";
  const isSwitchingKey = status === "switching_key";

  const title = isGaveUp
    ? t("workspace.ttsGaveUpTitle")
    : isSwitchingKey
      ? t("workspace.ttsSwitchingKeyTitle")
      : t("workspace.ttsRetryingTitle");
  const desc = isGaveUp
    ? t("workspace.ttsGaveUpDesc")
    : isSwitchingKey
      ? t("workspace.ttsSwitchingKeyDesc")
      : t("workspace.ttsRetryingDesc");

  return (
    <div
      className="absolute inset-0 z-30 flex items-center justify-center bg-background/60 backdrop-blur-sm"
      role="status"
      aria-live="polite"
    >
      <div className="mx-4 flex max-w-sm flex-col items-center gap-3 rounded-2xl border bg-card px-6 py-5 text-center shadow-lg">
        {isGaveUp ? (
          <Sparkles className="h-6 w-6 text-primary" />
        ) : (
          <Loader2 className={`h-6 w-6 animate-spin text-primary ${isSwitchingKey ? "duration-500" : ""}`} />
        )}
        <p className="text-sm font-semibold text-foreground">{title}</p>
        <p className="text-xs text-muted-foreground">{desc}</p>
      </div>
    </div>
  );
}
