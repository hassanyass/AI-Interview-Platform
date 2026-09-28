import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ShieldAlert, Trash2 } from "lucide-react";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { AiCoreIcon } from "../../components/ui/AiCoreIcon";
import { ResponsiveTable, type ResponsiveColumn } from "../../components/ui/ResponsiveTable";
import type { JobCandidateRow } from "../../api/adminClient";

/**
 * Responsive plan R3-A (docs/responsive-design-plan.md §3): the candidates
 * table, lifted out of JobResultsPage so the page and the dev harness at
 * /dev/results-preview render the SAME component -- the JobSummary.tsx
 * precedent from R2-A. Without this the preview would carry its own copy of
 * seven column definitions and drift from the real page silently.
 *
 * The seven columns used to live in a plain <table> inside
 * `overflow-x-auto`, which is why the action column -- View Result and
 * delete, the only two things HR can DO from this page -- was the one
 * scrolled off-screen on a phone. ResponsiveTable keeps the table at `md`
 * and above and becomes a card list below it, with `actions` pinned at the
 * end of each card, so no action is ever off-screen.
 */

/** Score visualization per the guide's own words ("Use mostly Grey base,
 * Red progress, Maroon for high-level summaries... avoid rainbow
 * dashboards"): Hire is the high-value outcome (maroon), No Hire is the
 * one signal worth flagging (red), Consider/Mixed is genuinely neutral
 * (grey) -- not a three-color success/warning/destructive traffic light. */
function recommendationTone(recommendation: string | undefined): { text: string; dot: string } {
  if (recommendation === "Hire") return { text: "text-secondary", dot: "bg-secondary" };
  if (recommendation === "No Hire") return { text: "text-primary", dot: "bg-primary" };
  return { text: "text-muted-foreground", dot: "bg-muted-foreground" };
}

/** A finished interview is the only kind with a result to open. CREATED and
 *  IN_PROGRESS rows show "Pending" instead of a dead link. */
function isFinished(status: string): boolean {
  return status === "COMPLETED" || status === "TERMINATED";
}

export interface CandidatesTableProps {
  jobId: string | undefined;
  candidates: JobCandidateRow[];
  /** Opens the confirmation modal; the caller owns the actual delete. */
  onRequestDelete: (row: { sessionId: string; name: string }) => void;
}

export function CandidatesTable({ jobId, candidates, onRequestDelete }: CandidatesTableProps) {
  const { t } = useTranslation();

  const columns: ResponsiveColumn<JobCandidateRow>[] = [
    {
      key: "candidate",
      header: t("jobResults.columns.candidate"),
      primary: true,
      cell: (cand) => (
        <>
          <div className="font-medium text-foreground">{cand.candidate_name || t("jobResults.unknownCandidate")}</div>
          {/* An email is data, never truncated away: it wraps instead. */}
          <div className="mt-0.5 break-all text-xs text-muted-foreground">
            {cand.candidate_email || t("jobResults.noEmail")}
          </div>
        </>
      ),
    },
    {
      key: "status",
      header: t("jobResults.columns.status"),
      cell: (cand) => (
        <Badge variant={cand.status === "COMPLETED" ? "success" : "warning"}>
          {/* Unknown statuses fall back to the raw value rather than
              rendering a missing-key string, so a new backend status is
              legible here before anyone adds a translation for it. */}
          {t(`jobResults.status.${cand.status}`, { defaultValue: cand.status })}
        </Badge>
      ),
    },
    {
      key: "score",
      header: t("jobResults.columns.score"),
      cell: (cand) => {
        if (cand.overall_score === undefined || cand.overall_score === null) {
          return <span className="text-muted-foreground">-</span>;
        }
        const tone = recommendationTone(cand.recommendation);
        return (
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium tabular-nums">{cand.overall_score}/5</span>
            {/* Score visualization per the e& guide (Section 11):
                grey/red/maroon, not a green/amber/red traffic light -- a
                dot + label reads calmer than a filled pill for something
                that's really a status word, not an alert. */}
            <span className={`inline-flex items-center gap-1.5 text-xs font-semibold ${tone.text}`}>
              <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${tone.dot}`} />
              {/* Display only -- recommendationTone() above still switches on
                  the raw value, so translating this cannot change the color. */}
              {t(`jobResults.recommendation.${cand.recommendation}`, { defaultValue: cand.recommendation })}
            </span>
          </div>
        );
      },
    },
    {
      key: "evidence",
      header: t("jobResults.columns.evidence"),
      cell: (cand) =>
        cand.evidence_sufficiency !== undefined && cand.evidence_sufficiency !== null ? (
          <span className="tabular-nums">{(cand.evidence_sufficiency * 100).toFixed(0)}%</span>
        ) : (
          <span className="text-muted-foreground">-</span>
        ),
    },
    {
      key: "suggested",
      header: t("jobResults.columns.suggested"),
      cell: (cand) =>
        isFinished(cand.status) ? (
          <div className="flex flex-wrap items-center gap-2">
            {cand.suggested ? (
              <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-secondary">
                <AiCoreIcon className="h-3 w-3" /> {t("jobResults.yes")}
              </span>
            ) : (
              <Badge variant="outline">{t("jobResults.no")}</Badge>
            )}
            {cand.override_suggested !== undefined && cand.override_suggested !== null && (
              <span className="rounded-sm bg-primary/10 px-1.5 py-0.5 text-xs font-medium tracking-wide text-primary">
                {t("jobResults.override")}
              </span>
            )}
          </div>
        ) : (
          <span className="text-muted-foreground">-</span>
        ),
    },
    {
      key: "integrity",
      header: t("jobResults.columns.integrity"),
      cell: (cand) =>
        cand.flagged_for_review ? (
          <Badge variant="destructive" className="inline-flex items-center gap-1">
            <ShieldAlert className="h-3 w-3" /> {t("jobResults.flagged")}
          </Badge>
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
    {
      key: "action",
      header: t("jobResults.columns.action"),
      actions: true,
      // The Link is `inline-flex` because a bare <a> around a button
      // collapses to the text's own 17px box: the LINK -- what a screen
      // reader and a finger actually target -- was under 44px even though
      // the button inside was not. Caught by the harness at 768.
      cell: (cand) => (
        <>
          {isFinished(cand.status) ? (
            <Link to={`/admin/jobs/${jobId}/results/${cand.session_id}`} className="inline-flex">
              {/* 44px below `lg`, 40px from there -- the R2-A convention. */}
              <Button size="sm" variant="outline" className="h-11 px-4 lg:h-10">
                {t("jobResults.viewResult")}
              </Button>
            </Link>
          ) : (
            <span className="text-xs italic text-muted-foreground">{t("jobResults.pending")}</span>
          )}
          {/* Icon-only, quiet by default, red on hover -- a destructive
              action shouldn't compete visually with "View Result" on every
              row (e& guide Section 7: hierarchy, not equal-weight
              buttons). Confirmation modal guards the actual delete. */}
          <button
            type="button"
            onClick={() =>
              onRequestDelete({
                sessionId: cand.session_id,
                name: cand.candidate_name || t("jobResults.thisCandidate"),
              })
            }
            aria-label={t("jobResults.deleteCandidateNamed", {
              name: cand.candidate_name || t("jobResults.candidate"),
            })}
            title={t("jobResults.deleteCandidate")}
            className="touch-target flex h-11 w-11 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-primary/10 hover:text-primary lg:h-10 lg:w-10"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </>
      ),
    },
  ];

  // Seven columns fit neither a tablet-portrait well (718px) nor a
  // tablet-landscape one (702px -- at `lg` the sidebar stops being a
  // drawer and takes 256px back), so the card rendering runs to `xl`.
  // Measured, not guessed: see the R3-A verify record.
  return (
    <ResponsiveTable
      columns={columns}
      rows={candidates}
      rowKey={(cand) => cand.session_id}
      caption={t("jobResults.tableCaption")}
      breakpoint="xl"
      empty={<div className="p-8 text-center text-muted-foreground">{t("jobResults.noCandidates")}</div>}
    />
  );
}
