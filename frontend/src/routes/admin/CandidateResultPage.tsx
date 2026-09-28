import { useEffect, useRef, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { adminClient, type EvaluationDetail } from "../../api/adminClient";
import {
  ArrowLeft, Mail, Calendar, Settings2, Loader2, Save,
  ChevronDown, CheckCircle2, XCircle, SkipForward, RotateCw, Clock,
  Lightbulb, MessageCircle, Code2, MessagesSquare, PencilLine, AlertTriangle,
  VideoOff, ShieldAlert, Maximize2, EyeOff, Users, Smartphone, RefreshCw, AudioLines,
} from "lucide-react";
import { Button } from "../../components/ui/Button";
import { Badge } from "../../components/ui/Badge";
import { Card } from "../../components/ui/Card";
import { AiCoreIcon } from "../../components/ui/AiCoreIcon";

/**
 * Full redesign (2026-09-01, approved from the "Candidate Scorecard"
 * mockup canvas): the previous pass fixed contrast and reorganized into
 * three stacked tiers, but was still one narrow centered column of white
 * cards -- the layout itself never changed. This pass rebuilds the page
 * around a two-zone composition instead:
 *   - A sticky LEFT RAIL (identity, a real score numeral instead of a
 *     small ring gauge, the verdict, and quick section navigation) --
 *     using a soft-neutral panel (--accent) to tie compositionally to the
 *     app's own maroon chrome instead of floating in white space.
 *   - A wider RIGHT COLUMN for the actual evidence: the recording,
 *     overall assessment, a single grouped criteria list (rows, not
 *     seven repeated cards), and the quieter "Full Record" zone.
 * This uses the app's real width instead of stranding it as empty
 * margins either side of a narrow centered stack -- the specific
 * "placement" complaint that motivated the redesign.
 */

// Live-review fix: dropped the left-edge color-bar-per-outcome (border-s-4)
// treatment these rows used to carry -- a generic "accent rail on a rounded
// card" pattern, and redundant besides: the pill below already carries the
// outcome in color, icon, and label. A plain border reads calmer and the
// pill is still the single source of truth for status.
// R3-B: the labels left these maps for `candidateResult.outcome.*` /
// `candidateResult.integrity.*`. Both maps are module-level, where t()
// cannot be called, so each entry's KEY is now also its translation key and
// the call sites resolve it. The icon and tone stay here, where they belong.
const OUTCOME_STYLE: Record<string, { icon: typeof CheckCircle2; text: string; bg: string }> = {
  COMPLETED: { icon: CheckCircle2, text: "text-success", bg: "bg-success/10" },
  SKIPPED: { icon: SkipForward, text: "text-muted-foreground", bg: "bg-muted" },
  CHANGED: { icon: RotateCw, text: "text-warning", bg: "bg-warning/10" },
  TIME_EXPIRED: { icon: Clock, text: "text-warning", bg: "bg-warning/10" },
  NOT_ATTEMPTED: { icon: Clock, text: "text-muted-foreground", bg: "bg-muted" },
};

/** Falls back to NOT_ATTEMPTED / DEFAULT exactly as the lookups below do,
 *  so an unknown value from the backend still gets a real label. */
const outcomeKey = (outcome: string) => (outcome in OUTCOME_STYLE ? outcome : "NOT_ATTEMPTED");
const integrityKey = (eventType: string) => (eventType in INTEGRITY_EVENT_META ? eventType : "DEFAULT");

/** Aggregation/dashboard pass: both PR-B's events (FULLSCREEN_EXITED,
 * TAB_HIDDEN, WINDOW_BLURRED) and PR-D's (NO_FACE_DETECTED,
 * MULTIPLE_FACES_DETECTED) land in the same interview_events table, but
 * this is the first place either is actually surfaced to a reviewer --
 * before this section existed, a real fired event produced no visible
 * change anywhere in the admin UI. Multiple-faces is the one case with
 * meaningfully fewer benign explanations than the others (see
 * useFaceDetectionMonitor.ts's own severity comment), hence destructive
 * rather than warning tone. */
const INTEGRITY_EVENT_META: Record<string, { icon: typeof ShieldAlert; bg: string; text: string }> = {
  FULLSCREEN_EXITED: { icon: Maximize2, bg: "bg-warning/10", text: "text-warning" },
  TAB_HIDDEN: { icon: EyeOff, bg: "bg-warning/10", text: "text-warning" },
  WINDOW_BLURRED: { icon: EyeOff, bg: "bg-warning/10", text: "text-warning" },
  NO_FACE_DETECTED: { icon: VideoOff, bg: "bg-warning/10", text: "text-warning" },
  MULTIPLE_FACES_DETECTED: { icon: Users, bg: "bg-destructive/10", text: "text-destructive" },
  // Part 2 (docs/CURRENT_DECISIONS.md): threshold not yet calibrated
  // against a real capture -- see useFaceDetectionMonitor.ts's docstring.
  // "Suspected" in the label deliberately, not a bare "Looking away".
  HEAD_DOWN_SUSPECTED: { icon: Smartphone, bg: "bg-warning/10", text: "text-warning" },
  DEFAULT: { icon: ShieldAlert, bg: "bg-warning/10", text: "text-warning" },
};

function formatOffset(seconds: number) {
  const total = Math.max(0, Math.round(seconds));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

/* Score visualization, e& guide Section 11: "Use mostly Grey base, Red
 * progress, Maroon for high-level summaries... avoid rainbow
 * dashboards." One criterion score isn't itself the headline number
 * (that's the two numerals in the rail above) -- it's a supporting
 * breakdown, so it gets the calmer of the two brand accents (maroon) at
 * a consistent color; the bar's LENGTH is what communicates magnitude,
 * not a green-good/red-bad hue swap across five separate colors. */
const CRITERION_BAR_FILL = "bg-secondary";

/** candidate_profile_service.py falls back to the literal string
 * "Candidate" as full_name when a Supabase profile is auto-created with
 * no real name captured (e.g. an OTP/guest flow that never asked for
 * one). Rendered as-is next to this page's own headings, it reads like
 * the page swallowed a word -- not like a real (if generic) name. Treat
 * it the same as "no name at all" everywhere a display name is shown. */
function displayName(name: string | undefined | null): string | null {
  const trimmed = (name || "").trim();
  if (!trimmed || trimmed.toLowerCase() === "candidate") return null;
  return trimmed;
}

function initials(name: string | undefined | null) {
  const parts = (displayName(name) || "").split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  return (parts[0][0] + (parts[1]?.[0] || "")).toUpperCase();
}

/** Pure-CSS smooth expand/collapse -- no animation library available in this
 * project (confirmed: `animate-in`/`tailwindcss-animate` classes appear
 * elsewhere but the plugin isn't installed, so they're silently inert). */
function Collapsible({ open, children }: { open: boolean; children: React.ReactNode }) {
  return (
    <div className={`grid transition-[grid-template-rows] duration-200 ease-out ${open ? "grid-rows-[1fr]" : "grid-rows-[0fr]"}`}>
      <div className="overflow-hidden">{children}</div>
    </div>
  );
}

/** Shared disclosure row chrome for Technical Submission / Full Transcript
 * inside the quieter "Full Record" frame, so both toggle the same way
 * instead of each inventing its own header treatment. */
function RecordSection({
  title, open, onToggle, children,
}: { title: string; open: boolean; onToggle: () => void; children: React.ReactNode }) {
  return (
    <div>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="w-full flex items-center justify-between px-5 py-4 text-start hover:bg-muted/40 transition-colors"
      >
        <span className="text-sm font-semibold text-foreground">{title}</span>
        <ChevronDown className={`h-4 w-4 text-muted-foreground shrink-0 transition-transform duration-200 ${open ? "rotate-180" : ""}`} />
      </button>
      <Collapsible open={open}>{children}</Collapsible>
    </div>
  );
}

export default function CandidateResultPage() {
  const { t } = useTranslation();
  const { jobId, sessionId } = useParams<{ jobId: string; sessionId: string }>();
  const [result, setResult] = useState<EvaluationDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [isTranscriptOpen, setIsTranscriptOpen] = useState(false);
  const [isSubmissionOpen, setIsSubmissionOpen] = useState(false);
  const [expandedQuestionId, setExpandedQuestionId] = useState<string | null>(null);
  const [expandedCriterion, setExpandedCriterion] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);

  // Evaluation regeneration (2026-09-03).
  const [isRegenerating, setIsRegenerating] = useState(false);
  const [regenerateError, setRegenerateError] = useState("");

  // Manual refresh (2026-09-03 UX pass): distinct from the initial-load
  // isLoading -- that flag swaps the whole page for a skeleton, which
  // would be a jarring way to handle "let me re-check this result,"
  // especially right after an action taken ON this same page (an
  // override save, a regeneration) already refetches in place.
  const [isRefreshing, setIsRefreshing] = useState(false);

  /** Integrity Timeline row click: seeks the existing player above rather
   *  than duplicating a second video experience in this section. No
   *  autoplay -- jumping straight to playing audio on click is a rougher
   *  surprise than a reviewer pressing play themselves once positioned. */
  const seekRecordingTo = (seconds: number) => {
    const video = videoRef.current;
    if (!video) return;
    video.currentTime = seconds;
    video.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  // Override State
  const [isOverrideMode, setIsOverrideMode] = useState(false);
  const [overrideValue, setOverrideValue] = useState<"computed" | "true" | "false">("computed");
  const [overrideReason, setOverrideReason] = useState("");
  const [isSavingOverride, setIsSavingOverride] = useState(false);

  const fetchResult = async (isManualRefresh = false) => {
    if (!sessionId) return;
    if (isManualRefresh) setIsRefreshing(true);
    else setIsLoading(true);
    setError("");
    try {
      const data = await adminClient.getCandidateResult(sessionId);
      setResult(data);
      if (data.override_suggested !== undefined && data.override_suggested !== null) {
        setOverrideValue(data.override_suggested ? "true" : "false");
        setOverrideReason(data.override_reason || "");
      } else {
        setOverrideValue("computed");
        setOverrideReason("");
      }
    } catch (err: any) {
      setError(err.message || t("candidateResult.failedToLoad"));
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    fetchResult();
  }, [sessionId]);

  const handleRegenerateEvaluation = async () => {
    if (!sessionId) return;
    setIsRegenerating(true);
    setRegenerateError("");
    try {
      const data = await adminClient.regenerateEvaluation(sessionId);
      setResult(data);
    } catch (err: any) {
      setRegenerateError(err.message || t("candidateResult.failedToRegenerate"));
    } finally {
      setIsRegenerating(false);
    }
  };

  const handleSaveOverride = async () => {
    if (!sessionId) return;
    setIsSavingOverride(true);
    try {
      const valueToSave = overrideValue === "computed" ? null : overrideValue === "true";
      await adminClient.setSuggestedOverride(sessionId, valueToSave, overrideValue !== "computed" ? overrideReason : undefined);
      await fetchResult();
      setIsOverrideMode(false);
    } catch (err: any) {
      setError(err.message || t("candidateResult.failedToSaveOverride"));
    } finally {
      setIsSavingOverride(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex flex-col lg:flex-row gap-8 items-start animate-pulse">
        <div className="w-full lg:w-[300px] h-72 bg-card rounded-xl border border-border shrink-0"></div>
        <div className="flex-1 space-y-6 w-full">
          <div className="h-48 bg-card rounded-xl border border-border"></div>
          <div className="h-64 bg-card rounded-xl border border-border"></div>
        </div>
      </div>
    );
  }

  if (error || !result) {
    return (
      <div className="bg-destructive/10 border border-destructive/20 text-destructive p-4 rounded-md flex flex-col gap-4 items-start">
        <p>{error || t("candidateResult.unexpectedError")}</p>
        <Button variant="outline" className="h-11 lg:h-10" onClick={() => fetchResult()}>{t("candidateResult.retry")}</Button>
      </div>
    );
  }

  const computedSuggested = result.recommendation === "Hire";
  const hasOverride = result.override_suggested !== undefined && result.override_suggested !== null;
  const finalSuggested = hasOverride ? result.override_suggested! : computedSuggested;
  // Session-finalization-contract fix (2026-09-01): a TERMINATED/
  // DISCONNECTED session's Evaluation row may be the guaranteed
  // placeholder backend/backend/api/endpoints/internal.py's
  // _ensure_evaluation_placeholder() writes when the interview ended
  // before a full AI evaluation could run (candidate disconnected and
  // never resumed, or ended the session mid-interview) — call this out
  // explicitly rather than let it read like a normal, complete result.
  const isIncompleteSession = result.status === "TERMINATED" || result.status === "DISCONNECTED";
  const name = displayName(result.candidate_name) || t("candidateResult.unnamedCandidate");

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      {/* R3-B: one row from `sm` (desktop anatomy unchanged); below it the
          identity stacks over Refresh instead of squeezing a truncated NAME
          between two buttons. `inline-flex` on the Link because a bare <a>
          around a button collapses to a 17px box -- the R3-A finding. */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 flex-col items-start gap-3 sm:flex-row sm:items-center sm:gap-4">
          <Link to={`/admin/jobs/${jobId}/results`} className="inline-flex sm:shrink-0">
            <Button variant="outline" size="sm" className="h-11 shrink-0 gap-1.5 lg:h-10">
              {/* e& guide Section 16 (RTL requirements): "Mirrored
                  directional icons" -- confirmed via a real RTL render
                  that a static ArrowLeft points the wrong way once the
                  page flows right-to-left; "back" should point toward
                  where the reader came from, which is the right in RTL. */}
              <ArrowLeft className="h-4 w-4 rtl:rotate-180" /> {t("candidateResult.backToResults")}
            </Button>
          </Link>
          <div className="min-w-0">
            <p className="text-[11px] font-bold uppercase tracking-wider text-primary mb-0.5">
              {t("candidateResult.eyebrow", { job: result.job_title || t("candidateResult.unknownJob") })}
            </p>
            {/* A name is data: it wraps on phone rather than being cut, and
                only truncates from `sm`, where `title` keeps it reachable. */}
            <h1 className="text-2xl font-extrabold tracking-tight text-foreground sm:truncate" title={name}>{name}</h1>
          </div>
        </div>
        <Button
          variant="outline"
          size="sm"
          className="h-11 w-full shrink-0 gap-1.5 sm:w-auto lg:h-10"
          onClick={() => fetchResult(true)}
          disabled={isRefreshing}
        >
          <RefreshCw className={`h-4 w-4 ${isRefreshing ? "animate-spin" : ""}`} />
          {isRefreshing ? t("candidateResult.refreshing") : t("candidateResult.refresh")}
        </Button>
      </div>

      {isIncompleteSession && (
        <div className="flex items-start gap-3 rounded-xl border border-warning/30 bg-warning/10 p-4 text-sm text-foreground">
          <AlertTriangle className="h-5 w-5 shrink-0 text-warning mt-0.5" />
          <div>
            <p className="font-semibold">{t("candidateResult.incomplete.title")}</p>
            <p className="text-muted-foreground mt-0.5">
              {t("candidateResult.incomplete.body", {
                what: result.status === "DISCONNECTED"
                  ? t("candidateResult.incomplete.disconnected")
                  : t("candidateResult.incomplete.ended"),
              })}
            </p>
          </div>
        </div>
      )}

      <div className="flex flex-col lg:flex-row gap-8 items-start">

        {/* ─── Left rail: identity, score, verdict, quick nav ───────────
            A soft-neutral panel (--accent, the e& guide's own "secondary
            backgrounds / quiet sections" token) -- not white, not maroon
            -- so the summary panel reads as its own zone and echoes the
            sidebar's maroon without repeating a solid fill of it. Sticky
            so it stays in view down a long report. */}
        <aside className="w-full lg:w-[300px] shrink-0 lg:sticky lg:top-8 rounded-xl border border-border bg-accent/50 overflow-hidden">
          <div className="px-6 pt-7 pb-6 flex flex-col items-center text-center border-b border-border/70">
            <div className="h-16 w-16 rounded-full bg-primary/10 text-primary flex items-center justify-center text-xl font-bold mb-3">
              {initials(result.candidate_name)}
            </div>
            <h2 className="text-base font-bold text-foreground">{name}</h2>
            <p className="text-xs text-muted-foreground mt-1.5 flex items-center justify-center gap-1.5">
              {/* An email is data -- it wraps rather than truncating. */}
              <Mail className="h-3.5 w-3.5 shrink-0" /> <span className="min-w-0 break-all">{result.candidate_email || t("candidateResult.noEmail")}</span>
            </p>
            <p className="text-[11px] text-muted-foreground/80 mt-1 flex items-center justify-center gap-1.5">
              <Calendar className="h-3.5 w-3.5 shrink-0" />
              {result.completed_at ? new Date(result.completed_at).toLocaleString() : t("candidateResult.pendingDate")}
            </p>
          </div>

          {/* Score -- two numerals, deliberately at the same visual tier and
              clearly labeled, per the scoring-mechanism upgrade
              (CURRENT_DECISIONS.md): "Holistic Assessment" is the LLM's own
              independent judgment (overall_score, unchanged); "Criteria-
              Weighted" is the new, real, code-computed aggregate of the
              criteria breakdown below (weighted_score) -- two different
              brand colors (maroon / red) reinforce that these are two
              genuinely different numbers, not one number shown twice. This
              directly replaces the earlier single-numeral design that left
              the criteria breakdown as a disconnected second section with
              no visible relationship to the headline score. */}
          <div className="px-6 py-6 border-b border-border/70">
            <div className="grid grid-cols-2 gap-2 text-center">
              <div>
                <div className="flex items-baseline justify-center gap-1 leading-none">
                  <span className="text-3xl font-extrabold text-secondary tracking-tight">{result.overall_score ?? "—"}</span>
                  <span className="text-xs font-semibold text-muted-foreground">/5</span>
                </div>
                <p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mt-1.5">{t("candidateResult.score.holistic")}</p>
                <p className="text-[10px] text-muted-foreground/70 leading-tight">{t("candidateResult.score.holisticHint")}</p>
              </div>
              <div className="border-s border-border/70 ps-2">
                <div className="flex items-baseline justify-center gap-1 leading-none">
                  <span className="text-3xl font-extrabold text-primary tracking-tight">{result.weighted_score != null ? result.weighted_score.toFixed(1) : "—"}</span>
                  <span className="text-xs font-semibold text-muted-foreground">/5</span>
                </div>
                <p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mt-1.5">{t("candidateResult.score.weighted")}</p>
                <p className="text-[10px] text-muted-foreground/70 leading-tight">{t("candidateResult.score.weightedHint")}</p>
              </div>
            </div>
            {(result.overall_score == null || result.weighted_score == null) && (
              <p className="text-[11px] text-muted-foreground text-center mt-3">
                {result.overall_score == null && result.weighted_score == null
                  ? t("candidateResult.score.neither")
                  : result.overall_score == null
                  ? t("candidateResult.score.noHolistic")
                  : t("candidateResult.score.noWeighted")}
              </p>
            )}
            <div className="flex flex-col items-center mt-5">
            {/* Verdict pill, e& score-visualization system (Section 11):
                "Grey base, Red progress, Maroon for high-level summaries"
                -- green never appears in that palette at all. Proceed is
                the high-value outcome (maroon, solid); Do Not Proceed is
                a plain neutral state, not an alarm (grey outline). */}
            <span className={`inline-flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-xs font-bold ${finalSuggested ? "bg-secondary text-secondary-foreground" : "bg-muted text-foreground border border-border"}`}>
              {finalSuggested ? <CheckCircle2 className="h-3.5 w-3.5" /> : <XCircle className="h-3.5 w-3.5" />}
              {finalSuggested ? t("candidateResult.score.proceed") : t("candidateResult.score.doNotProceed")}
            </span>
            {result.recommendation && (
              <p className="text-xs text-muted-foreground mt-3 flex items-center justify-center gap-1.5">
                <AiCoreIcon /> {t("candidateResult.score.aiRecommendation")} <span className="font-semibold text-foreground">{t(`jobResults.recommendation.${result.recommendation}`, { defaultValue: result.recommendation })}</span>
              </p>
            )}
            {hasOverride && (
              <div className="w-full mt-4 pt-4 border-t border-border/70 flex items-start gap-2 text-start">
                <Badge className="shrink-0 mt-0.5">{t("candidateResult.score.manualOverride")}</Badge>
                <p className="text-xs text-muted-foreground">{result.override_reason}</p>
              </div>
            )}
            </div>
          </div>

          {/* R3-B (user decision): hidden below `lg`. These anchors only
              earn their place while the rail is sticky; below that the rail
              sits above the content, so they are a block of links before any
              evidence. Nothing becomes unreachable -- scrolling is the
              replacement -- which is why hiding is allowed here at all. */}
          <nav className="hidden px-3 py-4 lg:flex lg:flex-col lg:gap-0.5">
            <p className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground/70 px-2 mb-1">{t("candidateResult.nav.onThisPage")}</p>
            <a href="#recording" className="flex items-center px-2.5 py-2.5 rounded-md text-sm font-medium text-foreground hover:bg-background transition-colors">{t("candidateResult.nav.recording")}</a>
            <a href="#criteria" className="flex items-center px-2.5 py-2.5 rounded-md text-sm font-medium text-foreground hover:bg-background transition-colors">{t("candidateResult.nav.criteria")}</a>
            <a href="#full-record" className="flex items-center px-2.5 py-2.5 rounded-md text-sm font-medium text-foreground hover:bg-background transition-colors">{t("candidateResult.nav.fullRecord")}</a>
          </nav>
        </aside>

        {/* ─── Right column: the evidence ─────────────────────────────── */}
        <div className="flex-1 min-w-0 w-full flex flex-col gap-6">

          <div id="recording" className="flex flex-col gap-6 scroll-mt-8">
            {/* Design pass (2026-09-03): a small voice-interview motif --
                nothing on this page previously signaled that this was a
                spoken interview at all, despite that being the product's
                actual core differentiator. Sits directly on the recording
                zone's own dark surface rather than adding a new card. */}
            <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              <AudioLines className="h-3.5 w-3.5 text-primary" /> {t("candidateResult.recording.eyebrow")}
            </div>
            {/* Recording playback: recording_url is a short-lived presigned
                GET URL computed fresh by the backend on every fetch of this
                page. null/undefined is a real, non-error state (R2 wasn't
                configured when this interview ran, the candidate denied
                camera permission, or Egress never started) per
                CURRENT_DECISIONS.md's camera-denial-degrades-gracefully
                decision. A dark player surface deliberately breaks from the
                page's white-card system -- it's a screen, not a document. */}
            <div className="rounded-xl overflow-hidden border border-border bg-[#171310]">
              {result.recording_url ? (
                <video
                  ref={videoRef}
                  controls
                  preload="metadata"
                  className="w-full max-h-[440px] block"
                  src={result.recording_url}
                >
                  {t("candidateResult.recording.unsupported")}
                </video>
              ) : result.is_mock_data ? (
                <div className="p-5 flex items-center gap-3 text-sm text-white/70">
                  <AiCoreIcon />
                  {t("candidateResult.recording.mockData")}
                </div>
              ) : (
                <div className="p-5 flex items-center gap-3 text-sm text-white/70">
                  <VideoOff className="h-5 w-5 shrink-0" />
                  {t("candidateResult.recording.none")}
                </div>
              )}
            </div>

            {/* Override -- a slim inline control, not a full-weight card
                competing with the evidence around it. */}
            <div className="rounded-xl border border-border bg-background px-5 py-3.5">
              {isOverrideMode ? (
                <div className="space-y-4 py-1">
                  <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                    <Settings2 className="h-4 w-4" /> {t("candidateResult.override.editTitle")}
                  </div>
                  <div className="space-y-2">
                    {/* R3-B: `htmlFor`/`id` -- the control had no accessible
                        name at all, so a screen reader announced a bare
                        combobox. 16px text on phone because anything smaller
                        makes iOS zoom the page on focus. */}
                    <label htmlFor="override-value" className="text-sm font-medium">{t("candidateResult.override.suggestedNextStep")}</label>
                    <select
                      id="override-value"
                      className="flex h-11 w-full rounded-md border border-input bg-transparent px-3 py-2 text-base ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 sm:text-sm lg:h-10"
                      value={overrideValue}
                      onChange={(e) => setOverrideValue(e.target.value as any)}
                    >
                      <option value="computed">{t("candidateResult.override.useComputed", { value: computedSuggested ? t("candidateResult.yes") : t("candidateResult.no") })}</option>
                      <option value="true">{t("candidateResult.override.forceYes")}</option>
                      <option value="false">{t("candidateResult.override.forceNo")}</option>
                    </select>
                  </div>

                  {overrideValue !== "computed" && (
                    <div className="space-y-2">
                      <label htmlFor="override-reason" className="text-sm font-medium">{t("candidateResult.override.reasonLabel")}</label>
                      <textarea
                        id="override-reason"
                        className="flex min-h-[80px] w-full rounded-md border border-input bg-transparent px-3 py-2 text-base ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 sm:text-sm"
                        placeholder={t("candidateResult.override.reasonPlaceholder")}
                        value={overrideReason}
                        onChange={(e) => setOverrideReason(e.target.value)}
                      />
                    </div>
                  )}

                  <div className="flex flex-wrap items-center gap-2 pt-1">
                    <Button
                      className="h-11 lg:h-10"
                      onClick={handleSaveOverride}
                      disabled={isSavingOverride || (overrideValue !== "computed" && !overrideReason.trim())}
                    >
                      {/* me-2, not mr-2: this flips with the writing direction. */}
                      {isSavingOverride ? <Loader2 className="h-4 w-4 animate-spin me-2" /> : <Save className="h-4 w-4 me-2" />}
                      {t("candidateResult.override.save")}
                    </Button>
                    <Button variant="outline" className="h-11 lg:h-10" onClick={() => {
                      setIsOverrideMode(false);
                      setOverrideValue(hasOverride ? (result.override_suggested ? "true" : "false") : "computed");
                      setOverrideReason(result.override_reason || "");
                    }}>
                      {t("candidateResult.override.cancel")}
                    </Button>
                  </div>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => setIsOverrideMode(true)}
                  className="touch-target -my-1 flex w-full items-center justify-between gap-3 py-1 text-start text-sm text-muted-foreground transition-colors hover:text-foreground"
                >
                  <span className="flex items-center gap-2"><PencilLine className="h-4 w-4 shrink-0" /> {hasOverride ? t("candidateResult.override.edit") : t("candidateResult.override.set")}</span>
                  <span className="shrink-0 text-primary font-medium">{hasOverride ? t("candidateResult.override.editShort") : t("candidateResult.override.setShort")}</span>
                </button>
              )}
            </div>

            {/* Integrity Timeline -- aggregation/dashboard pass. See
                INTEGRITY_EVENT_META's comment for why this exists. An
                empty list is the common, unremarkable case (per
                adminClient.ts's IntegrityEvent doc), not an error state,
                so it gets a plain reassuring line rather than an
                "empty state" illustration treatment. */}
            <div className="rounded-xl border border-border bg-background p-6">
              <div className="flex items-center justify-between mb-3">
                <p className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">{t("candidateResult.integrity.title")}</p>
                {result.integrity_events.length > 0 && (
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-warning/10 px-2.5 py-1 text-xs font-semibold text-warning">
                    <ShieldAlert className="h-3.5 w-3.5" />
                    {t("candidateResult.integrity.flagged", { count: result.integrity_events.length })}
                  </span>
                )}
              </div>
              {result.integrity_events.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  {t("candidateResult.integrity.none")}
                </p>
              ) : (
                <div className="-mx-6 divide-y divide-border">
                  {result.integrity_events.map((event, idx) => {
                    const meta = INTEGRITY_EVENT_META[event.event_type] || INTEGRITY_EVENT_META.DEFAULT;
                    const Icon = meta.icon;
                    const canSeek = Boolean(result.recording_url) && event.video_offset_seconds != null;
                    return (
                      <button
                        key={idx}
                        type="button"
                        onClick={() => canSeek && seekRecordingTo(event.video_offset_seconds!)}
                        disabled={!canSeek}
                        className={`w-full flex items-center gap-3 px-6 py-3 text-start transition-colors ${canSeek ? "hover:bg-muted/30 cursor-pointer" : "cursor-default"}`}
                      >
                        <span className={`shrink-0 h-8 w-8 rounded-full flex items-center justify-center ${meta.bg} ${meta.text}`}>
                          <Icon className="h-4 w-4" />
                        </span>
                        <span className="flex-1 min-w-0">
                          <span className="block text-sm font-medium text-foreground">{t(`candidateResult.integrity.${integrityKey(event.event_type)}`)}</span>
                          {event.phase && <span className="block text-xs text-muted-foreground mt-0.5">{event.phase}</span>}
                        </span>
                        <span className="shrink-0 text-xs font-semibold text-muted-foreground tabular-nums">
                          {event.video_offset_seconds != null ? formatOffset(event.video_offset_seconds) : "—"}
                        </span>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>

            <div className="rounded-xl border border-border bg-background p-6">
              <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
                <p className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">{t("candidateResult.assessment.title")}</p>
                {result.is_placeholder && (
                  // Design pass (2026-09-03): the guide's primary-button
                  // color (e& Red) is reserved for real, meaningful actions
                  // -- "Start Interview, Continue, Practice Again" are its
                  // own examples. This is the one genuine primary action
                  // on this page, not a secondary/outline-weight control.
                  <Button
                    size="sm"
                    variant="primary"
                    className="h-11 lg:h-10"
                    onClick={handleRegenerateEvaluation}
                    disabled={isRegenerating}
                  >
                    {isRegenerating ? <Loader2 className="h-3.5 w-3.5 me-1.5 animate-spin" /> : <RotateCw className="h-3.5 w-3.5 me-1.5" />}
                    {isRegenerating ? t("candidateResult.assessment.regenerating") : t("candidateResult.assessment.regenerate")}
                  </Button>
                )}
              </div>
              {/* Evaluation regeneration (2026-09-03): this evaluation is
                  still the generic _ensure_evaluation_placeholder row --
                  the session never got a real AI evaluation (crashed, lost
                  its lease, or ended via a path that never talks to the
                  agent, e.g. a candidate-terminated or idle-disconnected
                  session). The transcript/question records below are real
                  (see the results-display fix this follows) even though
                  this summary isn't yet -- the button generates a real one
                  from that same evidence. */}
              {result.is_placeholder && (
                <div className="mb-3 flex items-start gap-2 rounded-lg border border-warning/30 bg-warning/10 px-3.5 py-2.5 text-sm text-foreground">
                  <AlertTriangle className="h-4 w-4 shrink-0 text-warning mt-0.5" />
                  <p>{t("candidateResult.assessment.placeholderWarning")}</p>
                </div>
              )}
              {regenerateError && (
                <p className="mb-3 text-sm text-destructive">{regenerateError}</p>
              )}
              <p className="text-foreground leading-relaxed font-medium">{result.summary || t("candidateResult.assessment.noSummary")}</p>
              {result.detailed_overview && (
                <p className="text-sm text-muted-foreground leading-relaxed whitespace-pre-line mt-3">{result.detailed_overview}</p>
              )}
              {result.evidence_sufficiency != null && (
                <p className="text-xs text-muted-foreground pt-3 mt-3 border-t border-border">
                  {t("candidateResult.assessment.evidenceNote", { percent: Math.round(result.evidence_sufficiency * 100) })}
                </p>
              )}
            </div>
          </div>

          {/* Criteria Breakdown -- one grouped list of rows, not seven
              repeated cards. Collapsed by default; a row expands to its
              overview/strengths/improvements only when clicked. */}
          <div id="criteria" className="scroll-mt-8">
            <h3 className="text-lg font-bold tracking-tight mb-3">{t("candidateResult.criteria.title")}</h3>
            {result.scores.length === 0 ? (
              <div className="p-8 text-center text-muted-foreground border rounded-xl border-dashed">
                {t("candidateResult.criteria.none")}
              </div>
            ) : (
              <div className="rounded-xl border border-border bg-background overflow-hidden divide-y divide-border">
                {result.scores.map((score, idx) => {
                  const key = score.criterion_key || String(idx);
                  const isOpen = expandedCriterion === key;
                  const hasDetail = Boolean(score.overview) || score.strengths.length > 0 || score.improvements.length > 0;
                  return (
                    <div key={key}>
                      <button
                        type="button"
                        onClick={() => hasDetail && setExpandedCriterion(isOpen ? null : key)}
                        aria-expanded={isOpen}
                        className={`w-full flex items-start gap-3 px-4 py-4 text-start transition-colors sm:items-center sm:gap-4 sm:px-5 ${hasDetail ? "hover:bg-muted/30 cursor-pointer" : "cursor-default"}`}
                      >
                        {/* R3-B: one line from `sm`, two below it. At 375 the
                            old single row left ~71px for the bar and cut the
                            label at 160px; now the label gets a full line and
                            the bar+score get the next one. Spans, not divs: a
                            <button> may only contain phrasing content. */}
                        <span className="flex min-w-0 flex-1 flex-col gap-2 sm:flex-row sm:items-center sm:gap-4">
                          {/* Weight shown right on the label -- this is what
                              actually connects the weighted score above to
                              this breakdown: the visible arithmetic behind
                              it, not a second disconnected number. */}
                          <span
                            className="block text-sm font-semibold text-foreground sm:w-48 sm:shrink-0 sm:truncate"
                            title={score.criterion_label || score.criterion_key}
                          >
                            {score.criterion_label || score.criterion_key}
                            {score.weight != null && (
                              <span className="text-xs font-normal text-muted-foreground"> · {t("candidateResult.criteria.weight", { weight: score.weight })}</span>
                            )}
                          </span>
                          {score.score != null ? (
                            <span className="flex min-w-0 items-center gap-3 sm:flex-1">
                              <span className="relative block h-2 flex-1 overflow-hidden rounded-full bg-muted">
                                <span className={`absolute inset-y-0 start-0 rounded-full ${CRITERION_BAR_FILL}`} style={{ width: `${(score.score / 5) * 100}%` }} />
                              </span>
                              <span className="w-10 shrink-0 text-end text-sm font-bold text-foreground tabular-nums">{score.score}/5</span>
                            </span>
                          ) : (
                            <span className="block text-xs font-medium text-muted-foreground sm:flex-1">{t("candidateResult.criteria.noEvidence")}</span>
                          )}
                        </span>
                        {hasDetail && (
                          <ChevronDown className={`h-4 w-4 text-muted-foreground shrink-0 mt-1 transition-transform duration-200 sm:mt-0 ${isOpen ? "rotate-180" : ""}`} />
                        )}
                      </button>
                      <Collapsible open={isOpen}>
                        <div className="px-5 pb-5 pt-1 border-t border-border/70 space-y-3">
                          {score.overview && <p className="text-sm text-muted-foreground leading-relaxed">{score.overview}</p>}
                          {(score.strengths.length > 0 || score.improvements.length > 0) && (
                            <div className="grid sm:grid-cols-2 gap-4">
                              {score.strengths.length > 0 && (
                                <div>
                                  <p className="text-xs font-semibold text-success uppercase tracking-wider mb-1">{t("candidateResult.criteria.strengths")}</p>
                                  <ul className="list-disc list-inside text-sm text-foreground space-y-1">
                                    {score.strengths.map((s, i) => <li key={i}>{s}</li>)}
                                  </ul>
                                </div>
                              )}
                              {score.improvements.length > 0 && (
                                <div>
                                  <p className="text-xs font-semibold text-warning uppercase tracking-wider mb-1">{t("candidateResult.criteria.improvements")}</p>
                                  <ul className="list-disc list-inside text-sm text-foreground space-y-1">
                                    {score.improvements.map((s, i) => <li key={i}>{s}</li>)}
                                  </ul>
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      </Collapsible>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Full Record -- question-by-question detail, the technical
              submission, and the full transcript: genuinely useful, but
              the least-scanned part of the page. Grouped under one
              visibly quieter frame (dashed border, muted wash, no shadow)
              instead of more cards at the same weight as the evidence
              above. Technical Submission collapses by default too,
              matching the transcript's existing pattern. */}
          <div id="full-record" className="rounded-xl border border-dashed border-border bg-muted/20 scroll-mt-8">
            <div className="px-5 pt-5 pb-1">
              <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t("candidateResult.record.title")}</p>
              <p className="text-xs text-muted-foreground/80 mt-0.5">{t("candidateResult.record.subtitle")}</p>
            </div>

            <div className="px-5 pb-5 pt-3">
              <div className="flex items-center gap-2 mb-3">
                <MessagesSquare className="h-4 w-4 text-muted-foreground" />
                <h3 className="text-sm font-semibold text-foreground">{t("candidateResult.record.questionReview")}</h3>
              </div>
              {result.question_records.length === 0 ? (
                <div className="p-6 text-center text-sm text-muted-foreground border rounded-xl border-dashed bg-background">
                  {t("candidateResult.record.noQuestions")}
                </div>
              ) : (
                <div className="space-y-2">
                  {/* Verbal Background subsection: when the session opened with
                      CV-grounded background questions, group the rows under
                      Background / Discussion so HR reads the warm-up apart from
                      the assessed questions. Numbering restarts per group. */}
                  {result.question_records.map((record, idx) => {
                    const hasBackground = result.question_records.some((r) => r.subsection === "BACKGROUND");
                    const isBackground = record.subsection === "BACKGROUND";
                    const prev = idx > 0 ? result.question_records[idx - 1] : null;
                    const groupStart = hasBackground && (idx === 0 || (prev?.subsection === "BACKGROUND") !== isBackground);
                    const groupIndex = hasBackground
                      ? result.question_records.slice(0, idx + 1).filter((r) => (r.subsection === "BACKGROUND") === isBackground).length
                      : (record.order_index ?? idx) + 1;
                    const style = OUTCOME_STYLE[record.outcome] || OUTCOME_STYLE.NOT_ATTEMPTED;
                    const OutcomeIcon = style.icon;
                    const isExpanded = expandedQuestionId === record.question_id;
                    const hasDetail = Boolean(record.text) || record.hints_used > 0 || record.followups_used > 0 || record.clarifications_used > 0;
                    return (
                      <div key={record.question_id || idx} className="space-y-2">
                      {groupStart && (
                        <p className="pt-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                          {isBackground ? t("candidateResult.record.background") : t("candidateResult.record.discussion")}
                        </p>
                      )}
                      <Card className="border-border shadow-sm overflow-hidden bg-background">
                        <button
                          type="button"
                          onClick={() => hasDetail && setExpandedQuestionId(isExpanded ? null : record.question_id)}
                          aria-expanded={isExpanded}
                          className={`w-full flex items-center gap-4 p-4 text-start transition-colors ${hasDetail ? "hover:bg-muted/30 cursor-pointer" : "cursor-default"}`}
                        >
                          <div className={`flex-shrink-0 h-9 w-9 rounded-full flex items-center justify-center text-sm font-semibold ${isBackground ? "bg-primary/10 text-primary" : "bg-muted text-muted-foreground"}`}>
                            {String(groupIndex).padStart(2, "0")}
                          </div>
                          <div className="min-w-0 flex-1">
                            {/* A question title may truncate -- it is a title
                                -- but `title` keeps the full text reachable. */}
                            <p className="font-medium text-foreground truncate" title={record.title || t("candidateResult.record.questionFallback", { index: idx + 1 })}>
                              {record.title || t("candidateResult.record.questionFallback", { index: idx + 1 })}
                            </p>
                            {record.competency && <p className="text-xs text-muted-foreground mt-0.5">{record.competency}</p>}
                          </div>
                          <span className={`inline-flex items-center gap-1.5 shrink-0 rounded-full px-2.5 py-1 text-xs font-medium ${style.bg} ${style.text}`}>
                            <OutcomeIcon className="h-3.5 w-3.5" /> {t(`candidateResult.outcome.${outcomeKey(record.outcome)}`)}
                          </span>
                          {hasDetail && (
                            <ChevronDown className={`h-4 w-4 text-muted-foreground shrink-0 transition-transform duration-200 ${isExpanded ? "rotate-180" : ""}`} />
                          )}
                        </button>
                        <Collapsible open={isExpanded}>
                          <div className="px-4 pb-4 pt-1 border-t border-border space-y-3">
                            {record.text && (
                              <p className="text-sm text-muted-foreground leading-6 whitespace-pre-line pt-3">{record.text}</p>
                            )}
                            {(record.hints_used > 0 || record.followups_used > 0 || record.clarifications_used > 0) && (
                              <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
                                {record.hints_used > 0 && (
                                  <span className="inline-flex items-center gap-1"><Lightbulb className="h-3.5 w-3.5" /> {t("candidateResult.record.hints", { count: record.hints_used })}</span>
                                )}
                                {record.followups_used > 0 && (
                                  <span className="inline-flex items-center gap-1"><MessageCircle className="h-3.5 w-3.5" /> {t("candidateResult.record.followups", { count: record.followups_used })}</span>
                                )}
                                {record.clarifications_used > 0 && (
                                  <span className="inline-flex items-center gap-1"><MessageCircle className="h-3.5 w-3.5" /> {t("candidateResult.record.clarifications", { count: record.clarifications_used })}</span>
                                )}
                              </div>
                            )}
                            <p className="text-xs text-muted-foreground">
                              {t("candidateResult.record.seeTranscript")}
                            </p>
                          </div>
                        </Collapsible>
                      </Card>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {(result.technical_submission?.code || result.transcript.length > 0) && (
              <div className="border-t border-border divide-y divide-border">
                {result.technical_submission?.code && (
                  <RecordSection
                    title={t("candidateResult.record.technicalSubmission")}
                    open={isSubmissionOpen}
                    onToggle={() => setIsSubmissionOpen((v) => !v)}
                  >
                    <div className="flex items-center gap-2 px-5 pb-3 text-xs text-muted-foreground">
                      <Code2 className="h-3.5 w-3.5" /> {result.technical_submission.language || t("candidateResult.record.codeSubmission")}
                    </div>
                    <pre className="max-h-96 overflow-auto bg-[#20252b] p-5 text-sm leading-6 text-white">{result.technical_submission.code}</pre>
                  </RecordSection>
                )}
                {result.transcript.length > 0 && (
                  <RecordSection
                    title={t("candidateResult.record.fullTranscript")}
                    open={isTranscriptOpen}
                    onToggle={() => setIsTranscriptOpen((v) => !v)}
                  >
                    <div className="divide-y divide-border">
                      {result.transcript.map((message, index) => (
                        <div key={`${message.speaker}-${index}`} className="p-5">
                          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                            {message.speaker === "agent" ? t("candidateResult.record.interviewer") : t("candidateResult.record.candidate")}
                          </p>
                          <p className="mt-2 whitespace-pre-line text-sm leading-7">{message.text}</p>
                        </div>
                      ))}
                    </div>
                  </RecordSection>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
