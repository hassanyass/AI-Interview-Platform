import { useEffect, useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { adminClient, type JobDetail } from "../../api/adminClient";
import { ArrowLeft, MapPin, Briefcase, Clock, AlertCircle, Rocket, Loader2, Users, Trash2, Pause, Play, RotateCcw } from "lucide-react";
import SectionsEditor from "./SectionsEditor";
import CriteriaEditor from "./CriteriaEditor";
import CandidateAccess from "./CandidateAccess";
import PublishSetupModal from "./PublishSetupModal";
import ConfirmDeleteModal from "./ConfirmDeleteModal";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { useTranslation } from "react-i18next";

export default function JobDetailPage() {
  const { t } = useTranslation();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
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
      if (err.message?.includes("404") || err.status === 404) {
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
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-4">
          <Link to="/admin/jobs">
            <Button variant="outline" className="p-2 h-10 w-10">
              <ArrowLeft className="h-5 w-5" />
            </Button>
          </Link>
          <div>
            <h1 className="text-3xl font-bold tracking-tight">{job.title}</h1>
            <div className="flex items-center gap-4 mt-2 text-sm text-muted-foreground">
              <Badge variant={job.status === "PUBLISHED" ? "success" : "warning"}>
                {job.status}
              </Badge>
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
                  <span>{job.definition.duration_minutes} {t('jobDetail.min')}</span>
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {job.status === "DRAFT" && (
            <Button
              onClick={handlePublishClick}
              disabled={isPublishing}
              className="inline-flex items-center gap-2 shrink-0"
            >
              {isPublishing ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Rocket className="h-4 w-4" />
              )}
              <span>{t('jobDetail.publish')}</span>
            </Button>
          )}

          {job.status === "PUBLISHED" && (
            <Button
              onClick={() => handleStatusChange("PAUSED")}
              variant="outline"
              className="inline-flex items-center gap-2 shrink-0 border-orange-200 text-orange-600 hover:bg-orange-50"
            >
              <Pause className="h-4 w-4" />
              <span>Pause Job</span>
            </Button>
          )}

          {job.status === "PAUSED" && (
            <Button
              onClick={() => handleStatusChange("PUBLISHED")}
              className="inline-flex items-center gap-2 shrink-0"
            >
              <Play className="h-4 w-4" />
              <span>Resume Job</span>
            </Button>
          )}

          {(job.status === "PUBLISHED" || job.status === "PAUSED") && (
            <Button
              onClick={() => handleStatusChange("DRAFT")}
              variant="outline"
              className="inline-flex items-center gap-2 shrink-0 border-muted-foreground/20"
            >
              <RotateCcw className="h-4 w-4" />
              <span>Unpublish</span>
            </Button>
          )}

          <Link to={`/admin/jobs/${job.id}/results`}>
            <Button variant="outline" className="inline-flex items-center gap-2 shrink-0 border-primary/20 hover:bg-primary/5">
              <Users className="h-4 w-4" />
              <span>View Results</span>
            </Button>
          </Link>

          <Button
            onClick={() => setIsDeleteDialogOpen(true)}
            variant="outline"
            className="inline-flex items-center gap-2 shrink-0 border-red-200 text-red-500 hover:bg-red-50"
          >
            <Trash2 className="h-4 w-4" />
            <span>Delete</span>
          </Button>
        </div>
      </div>

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
