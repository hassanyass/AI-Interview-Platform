import { Link } from "react-router-dom";
import { useState } from "react";
import { Plus } from "lucide-react";
import { AdminShell } from "../admin/AdminLayout";
import { Card, CardContent } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { JobCard, JobHeader } from "../admin/JobSummary";

/**
 * DEV-ONLY visual harness for the admin shell (registered in App.tsx only
 * under import.meta.env.DEV). Renders the REAL AdminShell (sidebar, header,
 * content well) without a Supabase session, around static copies of the
 * two admin headers that are widest on desktop -- the jobs list header
 * and the job-detail action bar -- plus one job card. Enough to judge the
 * shell (R1) and those header patterns (R2) at every viewport; the pages
 * themselves still need a real login. No API calls are made.
 */
const mockJob = {
  id: "job-preview", title: "Senior Machine Learning Engineer", status: "PUBLISHED",
  location: "Dubai, UAE", seniority: "Senior", definition: { duration_minutes: 30 },
};

export default function AdminPreview() {
  const [status, setStatus] = useState<"PUBLISHED" | "PAUSED" | "DRAFT">("PUBLISHED");
  return (
    <AdminShell onSignOut={() => {}}>
      <div data-responsive-ignore className="border-b bg-amber-50 px-4 py-1.5 text-xs text-amber-800 -mx-4 -mt-4 mb-6 sm:-mx-6 sm:-mt-6 lg:-mx-8 lg:-mt-8">
        <strong>DEV PREVIEW</strong> — admin shell with mock data (no saves). Job status: {status}
      </div>

      <div className="space-y-6 pb-24 lg:pb-0">
        {/* JobsListPage header */}
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">Jobs</h1>
            <p className="text-muted-foreground mt-1">Manage your open positions and interview definitions.</p>
          </div>
          <Link to="#" className="sm:shrink-0">
            <Button className="inline-flex h-11 w-full items-center justify-center gap-2 sm:w-auto lg:h-10">
              <Plus className="h-5 w-5" />
              <span>Create new job</span>
            </Button>
          </Link>
        </div>

        {/* Real JobCard / JobHeader (R2-A) with a mock job; buttons are inert. */}
        <JobCard job={mockJob} onDelete={() => {}} />

        <JobHeader
          job={{ ...mockJob, status }}
          isPublishing={false}
          onPublish={() => setStatus("PUBLISHED")}
          onStatusChange={setStatus}
          onDelete={() => {}}
        />

        {/* A wide block so the content well's own scrolling is visible */}
        <Card>
          <CardContent className="p-6">
            <p className="text-sm text-muted-foreground">
              Content well. The sidebar is a fixed 256px on every width today; this block shows how much
              room is left for the page at the current viewport.
            </p>
          </CardContent>
        </Card>
      </div>
    </AdminShell>
  );
}
