import { useEffect, useState } from "react";
import { useParams, Link, useNavigate, useLocation } from "react-router-dom";
import { adminClient, type JobDetail } from "../../api/adminClient";
import { ArrowLeft, AlertCircle } from "lucide-react";
import SectionsEditor from "./SectionsEditor";
import CriteriaEditor from "./CriteriaEditor";
import CandidateAccess from "./CandidateAccess";
import PublishSetupModal from "./PublishSetupModal";
import ConfirmDeleteModal from "./ConfirmDeleteModal";
import { Button } from "../../components/ui/Button";
import { JobHeader } from "./JobSummary";
import { useTranslation } from "react-i18next";

export default function JobDetailPage() {
  const { t } = useTranslation();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  // H2-E: JobCreatePage hands over a one-time notice (e.g. "duration not set") instead of alert().
  const notice: string | undefined = (location.state as { notice?: string } | null)?.notice;
  const [job, setJob] = useState<JobDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [isNotFound, setIsNotFound] = useState(false);
  const [isPublishing, setIsPublishing] = useState(false);
  const [publishError, setPublishError] = useState("");
  const [isSetupModalOpen, setIsSetupModalOpen] = useState(false);
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);

  const fetchJob = async () => {
    if (!id) return;
    // Only show the full-page loading skeleton on the initial load. Section
    // and question editors call this same fetchJob as their onRefresh after
    // every add/edit/delete/regenerate — if we also flip isLoading(true)
    // there, this component tree (SectionsEditor, QuestionEditor) gets
    // unmounted in favor of the skeleton and then remounted fresh once data
    // arrives, silently wiping their local UI state (e.g. which section is
    // expanded, an in-progress edit) after every single action.
    if (!job) {
      setIsLoading(true);
    }
    setError("");
    setIsNotFound(false);
    try {
      const data = await adminClient.getJob(id);
      setJob(data);
    } catch (err: any) {
      if (err.status === 404) {
        setIsNotFound(true);
      } else {
        setError(err.message || t('jobDetail.failedToLoad'));
      }
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchJob();
  }, [id]);

  const handlePublishClick = () => {
    if (!job) return;
    setIsSetupModalOpen(true);
  };

  const handleConfirmPublish = async (isPublic: boolean) => {
    if (!job || !job.definition) return;
    setIsPublishing(true);
    setPublishError("");
    try {
      // Step 1: Update the definition with the chosen access mode
      await adminClient.updateDefinition(job.definition.id, { is_public: isPublic });
      // Step 2: Publish the job
      await adminClient.publishJob(job.id);
      setIsSetupModalOpen(false);
      await fetchJob();
    } catch (err: any) {
      setPublishError(err.message || t('jobDetail.failedToPublish'));
    } finally {
      setIsPublishing(false);
    }
  };

  const handleStatusChange = async (newStatus: string) => {
    if (!job) return;
    try {
      setPublishError("");
      await adminClient.updateJobStatus(job.id, newStatus);
      await fetchJob();
    } catch (err: any) {
      setPublishError(err.message || "Failed to update job status");
    }
  };

  const handleDeleteJob = async () => {
    if (!job) return;
    
    try {
      await adminClient.deleteJob(job.id);
      navigate("/admin/jobs");
    } catch (err: any) {
      setPublishError(err.message || "Failed to delete job");
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="h-8 bg-muted rounded w-1/4"></div>
        <div className="h-32 bg-card border border-border rounded-lg"></div>
      </div>
    );
  }

  if (isNotFound) {
    return (
      <div className="text-center py-12 bg-card border border-border rounded-lg">
        <AlertCircle className="h-12 w-12 mx-auto text-red-500 mb-4 opacity-80" />
        <h3 className="text-xl font-semibold text-foreground">{t('jobDetail.jobNotFound')}</h3>
        <p className="text-muted-foreground mt-2 max-w-md mx-auto">
          {t('jobDetail.jobNotFoundDesc')}
        </p>
        <Link to="/admin/jobs">
          <Button variant="secondary" className="mt-6 inline-flex items-center gap-2">
            <ArrowLeft className="h-4 w-4" />
            <span>{t('jobDetail.backToJobs')}</span>
          </Button>
        </Link>
      </div>
    );
  }

  if (error || !job) {
    return (
      <div className="bg-red-500/10 border border-red-500/20 text-red-500 p-4 rounded-md flex flex-col gap-4 items-start">
        <p>{error || t('jobDetail.unexpectedError')}</p>
        <Button 
          variant="outline"
          onClick={fetchJob}
          className="bg-white/50 text-red-600 border-red-200 hover:bg-white"
        >
          {t('jobDetail.retry')}
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6 pb-24 lg:pb-0">
      {notice && (
        <div role="status" className="flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{notice}</span>
        </div>
      )}
      {/* R2-A: identity + action bar (JobSummary.tsx). Below lg the bar is
          pinned to the viewport bottom, hence the pb-24 on this page so
          the last editor is never hidden behind it. */}
      <JobHeader
        job={job}
        isPublishing={isPublishing}
        onPublish={handlePublishClick}
        onStatusChange={handleStatusChange}
        onDelete={() => setIsDeleteDialogOpen(true)}
      />

      {publishError && (
        <div className="bg-red-500/10 border border-red-500/20 text-red-500 p-3 rounded-md text-sm">
          {publishError}
        </div>
      )}

      {job.status === "PUBLISHED" && job.definition && (
        <CandidateAccess 
          jobId={job.id} 
          definition={job.definition} 
          onRefresh={fetchJob} 
        />
      )}

      {job.definition && (
        <CriteriaEditor
          jobId={job.id}
          status={job.status}
          onRefresh={fetchJob}
        />
      )}

      {job.definition && (
        <SectionsEditor 
          jobId={job.id} 
          definition={job.definition} 
          onRefresh={fetchJob} 
          status={job.status}
        />
      )}
      
      <PublishSetupModal 
        isOpen={isSetupModalOpen} 
        onClose={() => setIsSetupModalOpen(false)} 
        onConfirm={handleConfirmPublish} 
      />

      <ConfirmDeleteModal
        isOpen={isDeleteDialogOpen}
        onClose={() => setIsDeleteDialogOpen(false)}
        onConfirm={handleDeleteJob}
      />
    </div>
  );
}
