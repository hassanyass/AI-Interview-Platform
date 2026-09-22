import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { adminClient, type Job } from "../../api/adminClient";
import { Plus, Briefcase } from "lucide-react";
import { Card, CardContent } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { JobCard } from "./JobSummary";
import ConfirmDeleteModal from "./ConfirmDeleteModal";
import { useTranslation } from "react-i18next";

export default function JobsListPage() {
  const { t } = useTranslation();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [jobToDelete, setJobToDelete] = useState<string | null>(null);

  useEffect(() => {
    async function loadJobs() {
      try {
        const data = await adminClient.getJobs();
        setJobs(data);
      } catch (err: any) {
        setError(err.message || t('jobsList.failedToLoad'));
      } finally {
        setIsLoading(false);
      }
    }
    loadJobs();
  }, []);

  const handleDeleteJob = async () => {
    if (!jobToDelete) return;
    
    try {
      await adminClient.deleteJob(jobToDelete);
      setJobs((prev) => prev.filter((j) => j.id !== jobToDelete));
      setJobToDelete(null);
    } catch (err: any) {
      alert(err.message || "Failed to delete job");
    }
  };

  if (isLoading) {
    return <div className="animate-pulse">{t('jobsList.loading')}</div>;
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{t('jobsList.title')}</h1>
          <p className="text-muted-foreground mt-1">{t('jobsList.desc')}</p>
        </div>
        <Link to="/admin/jobs/new" className="sm:shrink-0">
          <Button className="inline-flex h-11 w-full items-center justify-center gap-2 sm:w-auto lg:h-10">
            <Plus className="h-5 w-5" />
            <span>{t('jobsList.createNewJob')}</span>
          </Button>
        </Link>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/20 text-red-500 p-4 rounded-md">
          {error}
        </div>
      )}

      {jobs.length === 0 && !error ? (
        <Card className="text-center py-16 border-dashed">
          <CardContent className="flex flex-col items-center justify-center pt-6">
            <div className="h-16 w-16 bg-muted rounded-full flex items-center justify-center mb-4">
              <Briefcase className="h-8 w-8 text-muted-foreground opacity-70" />
            </div>
            <h3 className="text-xl font-semibold">{t('jobsList.noJobsYet')}</h3>
            <p className="text-muted-foreground mt-2 max-w-sm mx-auto">{t('jobsList.getStarted')}</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4">
          {jobs.map((job) => (
            <JobCard key={job.id} job={job} onDelete={setJobToDelete} />
          ))}
        </div>
      )}

      <ConfirmDeleteModal
        isOpen={jobToDelete !== null}
        onClose={() => setJobToDelete(null)}
        onConfirm={handleDeleteJob}
      />
    </div>
  );
}
