import { Link } from "react-router-dom";
import { ArrowLeft, Briefcase, Clock, Loader2, MapPin, Pause, Play, Rocket, RotateCcw, Trash2, Users } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { Job } from "../../api/adminClient";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Card, CardContent } from "../../components/ui/Card";
import { ActionMenu } from "../../components/ui/ActionMenu";
import { useBreakpoint } from "../../lib/useMediaQuery";

/**
 * Responsive plan R2-A (docs/responsive-design-plan.md, feedback 2026-09-17):
 * the job's identity -- title, status, meta -- had one anatomy on the jobs
 * list and another on the job page, and both put the status badge inline
 * after the title (so it landed wherever the title happened to wrap) and
 * a non-wrapping meta row ("30 / min"). One anatomy now, used by both:
 *
 *   title                         -- wraps freely, nothing inline with it
 *   [status]  meta · meta · meta  -- status first, chips wrap, never split
 *
 * Plus the two containers that use it: JobCard (list row) and JobHeader
 * (job page identity + action bar). Extracted here so /dev/admin-preview
 * renders the real components, not copies.
 */

type JobLike = Pick<Job, "id" | "title" | "status" | "location" | "seniority"> & {
  definition?: { duration_minutes?: number } | null;
};

export function JobStatusBadge({ status }: { status: string }) {
  const { t } = useTranslation();
  const variant = status === "PUBLISHED" ? "success" : status === "PAUSED" ? "default" : "warning";
  const key = status === "PUBLISHED" ? "published" : status === "PAUSED" ? "paused" : status === "DRAFT" ? "draft" : null;
  return <Badge variant={variant}>{key ? t(`jobStatus.${key}`) : status}</Badge>;
}

export function JobMetaRow({ job, className = "" }: { job: JobLike; className?: string }) {
  const { t } = useTranslation();
  const minutes = job.definition?.duration_minutes;
  return (
    <div className={`flex flex-wrap items-center gap-x-4 gap-y-1.5 text-sm text-muted-foreground ${className}`}>
      <JobStatusBadge status={job.status} />
      {job.location && (
        <span className="inline-flex items-center gap-1 whitespace-nowrap"><MapPin className="h-4 w-4 shrink-0" />{job.location}</span>
      )}
      {job.seniority && (
        <span className="inline-flex items-center gap-1 whitespace-nowrap"><Briefcase className="h-4 w-4 shrink-0" />{job.seniority}</span>
      )}
      {minutes != null && (
        <span className="inline-flex items-center gap-1 whitespace-nowrap tabular-nums"><Clock className="h-4 w-4 shrink-0" />{minutes} {t('jobsList.min')}</span>
      )}
    </div>
  );
}

/** One row of the jobs list. Actions stack under the identity on phones
 *  (Results / Manage share the width, delete stays icon-only with a real
 *  label), sit beside it from `md`. */
export function JobCard({ job, onDelete }: { job: JobLike; onDelete: (id: string) => void }) {
  const { t } = useTranslation();
  return (
    <Card className="hover:border-primary/50 transition-colors">
      <CardContent className="flex flex-col gap-4 p-4 sm:p-6 md:flex-row md:items-center md:justify-between">
        <div className="min-w-0 space-y-2">
          <h3 className="text-lg font-semibold leading-snug sm:text-xl">{job.title}</h3>
          <JobMetaRow job={job} />
        </div>
        <div className="flex items-center gap-2 md:shrink-0">
          <Link to={`/admin/jobs/${job.id}/results`} className="flex-1 md:flex-none">
            <Button variant="outline" className="h-11 w-full px-5 md:w-auto lg:h-10">{t('jobsList.results')}</Button>
          </Link>
          <Link to={`/admin/jobs/${job.id}`} className="flex-1 md:flex-none">
            <Button variant="secondary" className="h-11 w-full px-5 md:w-auto lg:h-10">{t('jobsList.manage')}</Button>
          </Link>
          <Button
            variant="outline"
            className="touch-target h-11 w-11 shrink-0 border-red-200 px-0 text-red-500 hover:bg-red-50 lg:h-10 lg:w-10"
            onClick={() => onDelete(job.id)}
            aria-label={t('jobsList.deleteJob')}
            title={t('jobsList.deleteJob')}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

export interface JobHeaderProps {
  job: JobLike;
  isPublishing: boolean;
  onPublish: () => void;
  onStatusChange: (status: "PUBLISHED" | "PAUSED" | "DRAFT") => void;
  onDelete: () => void;
}

/** Job page identity + action bar. The bar is one primary (Publish /
 *  Pause / Resume), one secondary (View Results) and an overflow menu
 *  (Unpublish, Delete). Below `lg` it is pinned to the bottom of the
 *  viewport so the primary action is one tap away however far down the
 *  sections are; at `lg+` it sits beside the identity as before. */
export function JobHeader({ job, isPublishing, onPublish, onStatusChange, onDelete }: JobHeaderProps) {
  const { t } = useTranslation();
  const isLg = useBreakpoint("lg");

  const primary =
    job.status === "DRAFT" ? (
      <Button onClick={onPublish} disabled={isPublishing} className="inline-flex h-11 flex-1 items-center justify-center gap-2 lg:h-10 lg:flex-none">
        {isPublishing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Rocket className="h-4 w-4" />}
        <span>{t('jobDetail.publish')}</span>
      </Button>
    ) : job.status === "PUBLISHED" ? (
      <Button onClick={() => onStatusChange("PAUSED")} variant="outline" className="inline-flex h-11 flex-1 items-center justify-center gap-2 border-orange-200 text-orange-600 hover:bg-orange-50 lg:h-10 lg:flex-none">
        <Pause className="h-4 w-4" />
        <span>{t('jobDetail.pauseJob')}</span>
      </Button>
    ) : (
      <Button onClick={() => onStatusChange("PUBLISHED")} className="inline-flex h-11 flex-1 items-center justify-center gap-2 lg:h-10 lg:flex-none">
        <Play className="h-4 w-4" />
        <span>{t('jobDetail.resumeJob')}</span>
      </Button>
    );

  const menuItems = [
    ...(job.status === "PUBLISHED" || job.status === "PAUSED"
      ? [{ label: t('jobDetail.unpublish'), icon: <RotateCcw />, onSelect: () => onStatusChange("DRAFT") }]
      : []),
    { label: t('jobDetail.delete'), icon: <Trash2 />, onSelect: onDelete, destructive: true },
  ];

  return (
    <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
      <div className="flex min-w-0 items-start gap-3 sm:gap-4">
        <Link to="/admin/jobs" className="shrink-0">
          <Button variant="outline" className="touch-target h-11 w-11 p-0 lg:h-10 lg:w-10" aria-label={t('jobDetail.backToJobs')}>
            <ArrowLeft className="h-5 w-5 rtl:rotate-180" />
          </Button>
        </Link>
        <div className="min-w-0">
          <h1 className="text-2xl font-bold leading-tight tracking-tight sm:text-3xl">{job.title}</h1>
          <JobMetaRow job={job} className="mt-2" />
        </div>
      </div>

      <div
        className="fixed inset-x-0 bottom-0 z-30 flex items-center gap-2 border-t bg-background/95 px-4 py-3 pb-[calc(0.75rem+var(--safe-bottom))] backdrop-blur lg:static lg:inset-auto lg:z-auto lg:shrink-0 lg:border-0 lg:bg-transparent lg:p-0 lg:backdrop-blur-none"
        role="toolbar"
        aria-label={t('jobDetail.actions')}
      >
        {primary}
        <Link to={`/admin/jobs/${job.id}/results`} className="flex-1 lg:flex-none">
          <Button variant="outline" className="inline-flex h-11 w-full items-center justify-center gap-2 border-primary/20 hover:bg-primary/5 lg:h-10 lg:w-auto">
            <Users className="h-4 w-4" />
            <span>{t('jobDetail.viewResults')}</span>
          </Button>
        </Link>
        <ActionMenu items={menuItems} label={t('jobDetail.moreActions')} placement={isLg ? "down" : "up"} />
      </div>
    </div>
  );
}
