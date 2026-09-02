import { useEffect, useRef, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { adminClient, type EvaluationDetail } from "../../api/adminClient";
import {
  ArrowLeft, Mail, Calendar, Settings2, Loader2, Save,
  ChevronDown, CheckCircle2, XCircle, SkipForward, RotateCw, Clock,
  Lightbulb, MessageCircle, Code2, MessagesSquare, PencilLine, AlertTriangle,
  VideoOff, ShieldAlert, Maximize2, EyeOff, Users,
} from "lucide-react";
import { Button } from "../../components/ui/Button";
import { Badge } from "../../components/ui/Badge";
import { Card } from "../../components/ui/Card";

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
const OUTCOME_STYLE: Record<string, { icon: typeof CheckCircle2; text: string; bg: string; label: string }> = {
  COMPLETED: { icon: CheckCircle2, text: "text-success", bg: "bg-success/10", label: "Completed" },
  SKIPPED: { icon: SkipForward, text: "text-muted-foreground", bg: "bg-muted", label: "Skipped" },
  CHANGED: { icon: RotateCw, text: "text-warning", bg: "bg-warning/10", label: "Changed" },
  TIME_EXPIRED: { icon: Clock, text: "text-warning", bg: "bg-warning/10", label: "Time expired" },
  NOT_ATTEMPTED: { icon: Clock, text: "text-muted-foreground", bg: "bg-muted", label: "Not attempted" },
};

/** Aggregation/dashboard pass: both PR-B's events (FULLSCREEN_EXITED,
 * TAB_HIDDEN, WINDOW_BLURRED) and PR-D's (NO_FACE_DETECTED,
 * MULTIPLE_FACES_DETECTED) land in the same interview_events table, but
 * this is the first place either is actually surfaced to a reviewer --
 * before this section existed, a real fired event produced no visible
 * change anywhere in the admin UI. Multiple-faces is the one case with
 * meaningfully fewer benign explanations than the others (see
 * useFaceDetectionMonitor.ts's own severity comment), hence destructive
 * rather than warning tone. */
const INTEGRITY_EVENT_META: Record<string, { icon: typeof ShieldAlert; label: string; bg: string; text: string }> = {
  FULLSCREEN_EXITED: { icon: Maximize2, label: "Exited fullscreen", bg: "bg-warning/10", text: "text-warning" },
  TAB_HIDDEN: { icon: EyeOff, label: "Switched away from the interview tab", bg: "bg-warning/10", text: "text-warning" },
  WINDOW_BLURRED: { icon: EyeOff, label: "Window lost focus", bg: "bg-warning/10", text: "text-warning" },
  NO_FACE_DETECTED: { icon: VideoOff, label: "No face detected on camera", bg: "bg-warning/10", text: "text-warning" },
  MULTIPLE_FACES_DETECTED: { icon: Users, label: "Multiple faces detected on camera", bg: "bg-destructive/10", text: "text-destructive" },
  DEFAULT: { icon: ShieldAlert, label: "Integrity event", bg: "bg-warning/10", text: "text-warning" },
};

function formatOffset(seconds: number) {
  const total = Math.max(0, Math.round(seconds));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function scoreTone(score: number | null | undefined): "success" | "warning" | "destructive" | "muted" {
  if (score == null) return "muted";
  if (score >= 4) return "success";
  if (score >= 3) return "warning";
  return "destructive";
}

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
  const { jobId, sessionId } = useParams<{ jobId: string; sessionId: string }>();
  const [result, setResult] = useState<EvaluationDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [isTranscriptOpen, setIsTranscriptOpen] = useState(false);
  const [isSubmissionOpen, setIsSubmissionOpen] = useState(false);
  const [expandedQuestionId, setExpandedQuestionId] = useState<string | null>(null);
  const [expandedCriterion, setExpandedCriterion] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);

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

  const fetchResult = async () => {
    if (!sessionId) return;
    setIsLoading(true);
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
      setError(err.message || "Failed to load candidate result");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchResult();
  }, [sessionId]);

  const handleSaveOverride = async () => {
    if (!sessionId) return;
    setIsSavingOverride(true);
    try {
      const valueToSave = overrideValue === "computed" ? null : overrideValue === "true";
      await adminClient.setSuggestedOverride(sessionId, valueToSave, overrideValue !== "computed" ? overrideReason : undefined);
      await fetchResult();
      setIsOverrideMode(false);
    } catch (err: any) {
      setError(err.message || "Failed to save override");
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
        <p>{error || "An unexpected error occurred."}</p>
        <Button variant="outline" onClick={fetchResult}>Retry</Button>
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
  const name = displayName(result.candidate_name) || "Unnamed candidate";

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div className="flex items-center gap-4">
        <Link to={`/admin/jobs/${jobId}/results`}>
          <Button variant="outline" className="p-2 h-10 w-10 shrink-0" aria-label="Back to candidate list">
            <ArrowLeft className="h-5 w-5" />
          </Button>
        </Link>
        <div className="min-w-0">
          <p className="text-[11px] font-bold uppercase tracking-wider text-primary mb-0.5">
            {result.job_title || "Unknown Job"} · Candidate Result
          </p>
          <h1 className="text-2xl font-extrabold tracking-tight text-foreground truncate">{name}</h1>
        </div>
      </div>

      {isIncompleteSession && (
        <div className="flex items-start gap-3 rounded-xl border border-warning/30 bg-warning/10 p-4 text-sm text-foreground">
          <AlertTriangle className="h-5 w-5 shrink-0 text-warning mt-0.5" />
          <div>
            <p className="font-semibold">Incomplete session</p>
            <p className="text-muted-foreground mt-0.5">
              This interview {result.status === "DISCONNECTED" ? "was disconnected and never resumed" : "ended before all sections were completed"}.
              The score and summary below are based on partial evidence — review the transcript and recording directly before deciding.
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
              <Mail className="h-3.5 w-3.5 shrink-0" /> <span className="truncate">{result.candidate_email || "No email provided"}</span>
            </p>
            <p className="text-[11px] text-muted-foreground/80 mt-1 flex items-center justify-center gap-1.5">
              <Calendar className="h-3.5 w-3.5 shrink-0" />
              {result.completed_at ? new Date(result.completed_at).toLocaleString() : "Pending"}
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
                <p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mt-1.5">Holistic</p>
                <p className="text-[10px] text-muted-foreground/70 leading-tight">AI's overall judgment</p>
              </div>
              <div className="border-s border-border/70 ps-2">
                <div className="flex items-baseline justify-center gap-1 leading-none">
                  <span className="text-3xl font-extrabold text-primary tracking-tight">{result.weighted_score != null ? result.weighted_score.toFixed(1) : "—"}</span>
                  <span className="text-xs font-semibold text-muted-foreground">/5</span>
                </div>
                <p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mt-1.5">Weighted</p>
                <p className="text-[10px] text-muted-foreground/70 leading-tight">From your criteria</p>
              </div>
            </div>
            {(result.overall_score == null || result.weighted_score == null) && (
              <p className="text-[11px] text-muted-foreground text-center mt-3">
                {result.overall_score == null && result.weighted_score == null
                  ? "Not enough evidence to compute either score."
                  : result.overall_score == null
                  ? "Not enough evidence for a holistic score."
                  : "No scored criteria to compute a weighted score."}
              </p>
            )}
            <div className="flex flex-col items-center mt-5">
            <span className={`inline-flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-xs font-bold ${finalSuggested ? "bg-success text-success-foreground" : "bg-muted text-foreground border border-border"}`}>
              {finalSuggested ? <CheckCircle2 className="h-3.5 w-3.5" /> : <XCircle className="h-3.5 w-3.5" />}
              {finalSuggested ? "Proceed to Next Step" : "Do Not Proceed"}
            </span>
            {result.recommendation && (
              <p className="text-xs text-muted-foreground mt-3">AI recommendation: <span className="font-semibold text-foreground">{result.recommendation}</span></p>
            )}
            {hasOverride && (
              <div className="w-full mt-4 pt-4 border-t border-border/70 flex items-start gap-2 text-start">
                <Badge className="shrink-0 mt-0.5">Manual override</Badge>
                <p className="text-xs text-muted-foreground">{result.override_reason}</p>
              </div>
            )}
            </div>
          </div>

          <nav className="px-3 py-4 flex flex-col gap-0.5">
            <p className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground/70 px-2 mb-1">On this page</p>
            <a href="#recording" className="px-2.5 py-2 rounded-md text-sm font-medium text-foreground hover:bg-background transition-colors">Recording &amp; assessment</a>
            <a href="#criteria" className="px-2.5 py-2 rounded-md text-sm font-medium text-foreground hover:bg-background transition-colors">Criteria breakdown</a>
            <a href="#full-record" className="px-2.5 py-2 rounded-md text-sm font-medium text-foreground hover:bg-background transition-colors">Full record</a>
          </nav>
        </aside>

        {/* ─── Right column: the evidence ─────────────────────────────── */}
        <div className="flex-1 min-w-0 w-full flex flex-col gap-6">

          <div id="recording" className="flex flex-col gap-6 scroll-mt-8">
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
                  Your browser does not support video playback.
                </video>
              ) : (
                <div className="p-5 flex items-center gap-3 text-sm text-white/70">
                  <VideoOff className="h-5 w-5 shrink-0" />
                  No recording is available for this session (recording may not have been enabled, camera access was declined, or the recording failed to start).
                </div>
              )}
            </div>

            {/* Override -- a slim inline control, not a full-weight card
                competing with the evidence around it. */}
            <div className="rounded-xl border border-border bg-background px-5 py-3.5">
              {isOverrideMode ? (
                <div className="space-y-4 py-1">
                  <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                    <Settings2 className="h-4 w-4" /> Edit outcome override
                  </div>
                  <div className="space-y-2">
                    <label className="text-sm font-medium">Suggested Next Step</label>
                    <select
                      className="flex h-10 w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                      value={overrideValue}
                      onChange={(e) => setOverrideValue(e.target.value as any)}
                    >
                      <option value="computed">Use AI Computed Result ({computedSuggested ? "Yes" : "No"})</option>
                      <option value="true">Force Override: Yes</option>
                      <option value="false">Force Override: No</option>
                    </select>
                  </div>

                  {overrideValue !== "computed" && (
                    <div className="space-y-2">
                      <label className="text-sm font-medium">Override Reason (Required)</label>
                      <textarea
                        className="flex min-h-[80px] w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                        placeholder="Why are you overriding the AI's suggestion?"
                        value={overrideReason}
                        onChange={(e) => setOverrideReason(e.target.value)}
                      />
                    </div>
                  )}

                  <div className="flex items-center gap-2 pt-1">
                    <Button
                      onClick={handleSaveOverride}
                      disabled={isSavingOverride || (overrideValue !== "computed" && !overrideReason.trim())}
                    >
                      {isSavingOverride ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Save className="h-4 w-4 mr-2" />}
                      Save Changes
                    </Button>
                    <Button variant="outline" onClick={() => {
                      setIsOverrideMode(false);
                      setOverrideValue(hasOverride ? (result.override_suggested ? "true" : "false") : "computed");
                      setOverrideReason(result.override_reason || "");
                    }}>
                      Cancel
                    </Button>
                  </div>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => setIsOverrideMode(true)}
                  className="w-full flex items-center justify-between text-sm text-muted-foreground hover:text-foreground transition-colors"
                >
                  <span className="flex items-center gap-2"><PencilLine className="h-4 w-4" /> {hasOverride ? "Edit manual override" : "Override this suggestion manually"}</span>
                  <span className="text-primary font-medium">{hasOverride ? "Edit" : "Set override"}</span>
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
                <p className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">Integrity Timeline</p>
                {result.integrity_events.length > 0 && (
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-warning/10 px-2.5 py-1 text-xs font-semibold text-warning">
                    <ShieldAlert className="h-3.5 w-3.5" />
                    {result.integrity_events.length} flagged moment{result.integrity_events.length > 1 ? "s" : ""}
                  </span>
                )}
              </div>
              {result.integrity_events.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No integrity flags were recorded for this session — fullscreen, tab focus, and camera presence all stayed within bounds throughout.
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
                          <span className="block text-sm font-medium text-foreground">{meta.label}</span>
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
              <p className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground mb-3">Overall Assessment</p>
              <p className="text-foreground leading-relaxed font-medium">{result.summary || "No summary available."}</p>
              {result.detailed_overview && (
                <p className="text-sm text-muted-foreground leading-relaxed whitespace-pre-line mt-3">{result.detailed_overview}</p>
              )}
              {result.evidence_sufficiency != null && (
                <p className="text-xs text-muted-foreground pt-3 mt-3 border-t border-border">
                  Based on {Math.round(result.evidence_sufficiency * 100)}% of the assessed criteria having enough transcript evidence to score confidently.
                </p>
              )}
            </div>
          </div>

          {/* Criteria Breakdown -- one grouped list of rows, not seven
              repeated cards. Collapsed by default; a row expands to its
              overview/strengths/improvements only when clicked. */}
          <div id="criteria" className="scroll-mt-8">
            <h3 className="text-lg font-bold tracking-tight mb-3">Criteria Breakdown</h3>
            {result.scores.length === 0 ? (
              <div className="p-8 text-center text-muted-foreground border rounded-xl border-dashed">
                No scores available.
              </div>
            ) : (
              <div className="rounded-xl border border-border bg-background overflow-hidden divide-y divide-border">
                {result.scores.map((score, idx) => {
                  const tone = scoreTone(score.score);
                  const barClass = { success: "bg-success", warning: "bg-warning", destructive: "bg-destructive", muted: "bg-muted" }[tone];
                  const key = score.criterion_key || String(idx);
                  const isOpen = expandedCriterion === key;
                  const hasDetail = Boolean(score.overview) || score.strengths.length > 0 || score.improvements.length > 0;
                  return (
                    <div key={key}>
                      <button
                        type="button"
                        onClick={() => hasDetail && setExpandedCriterion(isOpen ? null : key)}
                        aria-expanded={isOpen}
                        className={`w-full flex items-center gap-4 px-5 py-4 text-start transition-colors ${hasDetail ? "hover:bg-muted/30 cursor-pointer" : "cursor-default"}`}
                      >
                        {/* Weight shown right on the label -- this is what
                            actually connects the weighted score above to
                            this breakdown: the visible arithmetic behind
                            it, not a second disconnected number. */}
                        <span className="w-40 sm:w-48 shrink-0 text-sm font-semibold text-foreground truncate">
                          {score.criterion_label || score.criterion_key}
                          {score.weight != null && (
                            <span className="text-xs font-normal text-muted-foreground"> · Weight {score.weight}</span>
                          )}
                        </span>
                        {score.score != null ? (
                          <>
                            <div className="flex-1 h-2 rounded-full bg-muted relative overflow-hidden">
                              <div className={`absolute inset-y-0 start-0 rounded-full ${barClass}`} style={{ width: `${(score.score / 5) * 100}%` }} />
                            </div>
                            <span className="w-10 shrink-0 text-end text-sm font-bold text-foreground tabular-nums">{score.score}/5</span>
                          </>
                        ) : (
                          <span className="flex-1 text-xs font-medium text-muted-foreground">No evidence</span>
                        )}
                        {hasDetail && (
                          <ChevronDown className={`h-4 w-4 text-muted-foreground shrink-0 transition-transform duration-200 ${isOpen ? "rotate-180" : ""}`} />
                        )}
                      </button>
                      <Collapsible open={isOpen}>
                        <div className="px-5 pb-5 pt-1 border-t border-border/70 space-y-3">
                          {score.overview && <p className="text-sm text-muted-foreground leading-relaxed">{score.overview}</p>}
                          {(score.strengths.length > 0 || score.improvements.length > 0) && (
                            <div className="grid sm:grid-cols-2 gap-4">
                              {score.strengths.length > 0 && (
                                <div>
                                  <p className="text-xs font-semibold text-success uppercase tracking-wider mb-1">Strengths</p>
                                  <ul className="list-disc list-inside text-sm text-foreground space-y-1">
                                    {score.strengths.map((s, i) => <li key={i}>{s}</li>)}
                                  </ul>
                                </div>
                              )}
                              {score.improvements.length > 0 && (
                                <div>
                                  <p className="text-xs font-semibold text-warning uppercase tracking-wider mb-1">Areas for Improvement</p>
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
              <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Full Record</p>
              <p className="text-xs text-muted-foreground/80 mt-0.5">Question-by-question detail, the technical submission, and the full transcript.</p>
            </div>

            <div className="px-5 pb-5 pt-3">
              <div className="flex items-center gap-2 mb-3">
                <MessagesSquare className="h-4 w-4 text-muted-foreground" />
                <h3 className="text-sm font-semibold text-foreground">Question-by-Question Review</h3>
              </div>
              {result.question_records.length === 0 ? (
                <div className="p-6 text-center text-sm text-muted-foreground border rounded-xl border-dashed bg-background">
                  No questions were recorded for this session.
                </div>
              ) : (
                <div className="space-y-2">
                  {result.question_records.map((record, idx) => {
                    const style = OUTCOME_STYLE[record.outcome] || OUTCOME_STYLE.NOT_ATTEMPTED;
                    const OutcomeIcon = style.icon;
                    const isExpanded = expandedQuestionId === record.question_id;
                    const hasDetail = Boolean(record.text) || record.hints_used > 0 || record.followups_used > 0 || record.clarifications_used > 0;
                    return (
                      <Card key={record.question_id || idx} className="border-border shadow-sm overflow-hidden bg-background">
                        <button
                          type="button"
                          onClick={() => hasDetail && setExpandedQuestionId(isExpanded ? null : record.question_id)}
                          aria-expanded={isExpanded}
                          className={`w-full flex items-center gap-4 p-4 text-start transition-colors ${hasDetail ? "hover:bg-muted/30 cursor-pointer" : "cursor-default"}`}
                        >
                          <div className="flex-shrink-0 h-9 w-9 rounded-full bg-muted flex items-center justify-center text-sm font-semibold text-muted-foreground">
                            {String((record.order_index ?? idx) + 1).padStart(2, "0")}
                          </div>
                          <div className="min-w-0 flex-1">
                            <p className="font-medium text-foreground truncate">{record.title || `Question ${idx + 1}`}</p>
                            {record.competency && <p className="text-xs text-muted-foreground mt-0.5">{record.competency}</p>}
                          </div>
                          <span className={`inline-flex items-center gap-1.5 shrink-0 rounded-full px-2.5 py-1 text-xs font-medium ${style.bg} ${style.text}`}>
                            <OutcomeIcon className="h-3.5 w-3.5" /> {style.label}
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
                                  <span className="inline-flex items-center gap-1"><Lightbulb className="h-3.5 w-3.5" /> {record.hints_used} hint{record.hints_used > 1 ? "s" : ""} used</span>
                                )}
                                {record.followups_used > 0 && (
                                  <span className="inline-flex items-center gap-1"><MessageCircle className="h-3.5 w-3.5" /> {record.followups_used} follow-up{record.followups_used > 1 ? "s" : ""}</span>
                                )}
                                {record.clarifications_used > 0 && (
                                  <span className="inline-flex items-center gap-1"><MessageCircle className="h-3.5 w-3.5" /> {record.clarifications_used} clarification{record.clarifications_used > 1 ? "s" : ""}</span>
                                )}
                              </div>
                            )}
                            <p className="text-xs text-muted-foreground">
                              See the full transcript below for exactly what the candidate said in response.
                            </p>
                          </div>
                        </Collapsible>
                      </Card>
                    );
                  })}
                </div>
              )}
            </div>

            {(result.technical_submission?.code || result.transcript.length > 0) && (
              <div className="border-t border-border divide-y divide-border">
                {result.technical_submission?.code && (
                  <RecordSection
                    title="Technical Submission"
                    open={isSubmissionOpen}
                    onToggle={() => setIsSubmissionOpen((v) => !v)}
                  >
                    <div className="flex items-center gap-2 px-5 pb-3 text-xs text-muted-foreground">
                      <Code2 className="h-3.5 w-3.5" /> {result.technical_submission.language || "Code submission"}
                    </div>
                    <pre className="max-h-96 overflow-auto bg-[#20252b] p-5 text-sm leading-6 text-white">{result.technical_submission.code}</pre>
                  </RecordSection>
                )}
                {result.transcript.length > 0 && (
                  <RecordSection
                    title="Full Interview Transcript"
                    open={isTranscriptOpen}
                    onToggle={() => setIsTranscriptOpen((v) => !v)}
                  >
                    <div className="divide-y divide-border">
                      {result.transcript.map((message, index) => (
                        <div key={`${message.speaker}-${index}`} className="p-5">
                          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                            {message.speaker === "agent" ? "Interviewer" : "Candidate"}
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
