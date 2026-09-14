import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { adminClient, type Job } from "../../api/adminClient";
import { Plus, Clock, MapPin, Briefcase, Trash2 } from "lucide-react";
import { Card, CardContent } from "../../components/ui/Card";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
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
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{t('jobsList.title')}</h1>
          <p className="text-muted-foreground mt-1">{t('jobsList.desc')}</p>
        </div>
          <Link to="/admin/jobs/new">
            <Button className="inline-flex items-center gap-2">
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
            <Card key={job.id} className="hover:border-primary/50 transition-colors group">
              <CardContent className="p-6 flex items-center justify-between m-0 pb-6 pt-6">
                <div className="space-y-2">
                  <div className="flex items-center gap-3">
                    <h3 className="text-xl font-semibold">{job.title}</h3>
                    <Badge variant={job.status === "PUBLISHED" ? "success" : "warning"}>
                      {job.status}
                    </Badge>
                  </div>
                <div className="flex items-center gap-4 text-sm text-muted-foreground">
                  {job.location && (
                    <div className="flex items-center gap-1">
                      <MapPin className="h-4 w-4" />
                      <span>{job.location}</span>
                    </div>
                  )}
                  {job.seniority && (
                    <div className="flex items-center gap-1">
                      <Briefcase className="h-4 w-4" />
                      <span>{job.seniority}</span>
                    </div>
                  )}
                  {job.definition && (
                    <div className="flex items-center gap-1">
                      <Clock className="h-4 w-4" />
                      <span>{job.definition.duration_minutes} {t('jobsList.min')}</span>
                    </div>
                  )}
                </div>
              </div>
                  <div className="flex items-center gap-2">
                    <Link to={`/admin/jobs/${job.id}/results`}>
                      <Button variant="outline" className="px-5">Results</Button>
                    </Link>
                    <Link to={`/admin/jobs/${job.id}`}>
                      <Button variant="secondary" className="px-5">{t('jobsList.manage')}</Button>
                    </Link>
                    <Button 
                      variant="outline" 
                      className="px-3 border-red-200 text-red-500 hover:bg-red-50"
                      onClick={() => setJobToDelete(job.id)}
                      title="Delete Job"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
              </CardContent>
            </Card>
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
