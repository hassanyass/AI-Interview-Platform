import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { FileText, Loader2, RefreshCw, UploadCloud } from "lucide-react";
import { Button } from "../../components/ui/Button";
import { getSessionCv, uploadSessionCv, type SessionCvStatus } from "../../services/api/interviews";

// Verbal Background subsection, step 2 (docs/verbal-background-subsection-
// plan.md §2 "Candidate (entry)", rulings Q1/Q2): the mandatory CV step
// between register/redeem and Start. One component, mounted by ApplyPage,
// InvitePage and -- as the refresh/direct-navigation fallback -- the
// InterviewSession intro. The backend refuses the room token until the
// session's application carries a CV (livekit.py), so this is a real gate,
// not a courtesy:
//   * PDF only, <= 5 MB (client check mirrors the server's), drag/drop or pick;
//   * failure is an inline error + retry, never a dead end;
//   * after a successful parse, a short "what we read" summary so a bad
//     parse is visible before the interview starts;
//   * an application that already carries a CV (invitee, or a returning
//     public applicant) is offered "use the CV we have" or replace.

export const CV_MAX_BYTES = 5 * 1024 * 1024;

interface CvUploadStepProps {
  sessionId: string;
  /** Called once the session has a CV and the candidate chose to continue. */
  onContinue: () => void;
  continueLabel?: string;
}

export function CvUploadStep({ sessionId, onContinue, continueLabel }: CvUploadStepProps) {
  const { t } = useTranslation();
  const [status, setStatus] = useState<SessionCvStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [replacing, setReplacing] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getSessionCv(sessionId)
      .then((s) => { if (!cancelled) setStatus(s); })
      .catch((err: any) => { if (!cancelled) setError(err.message || t("cv.loadFailed")); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [sessionId, t]);

  const handleFile = useCallback(async (file: File | null | undefined) => {
    if (!file) return;
    setError("");
    const isPdf = file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
    if (!isPdf) { setError(t("cv.errorNotPdf")); return; }
    if (file.size > CV_MAX_BYTES) { setError(t("cv.errorTooLarge")); return; }
    setUploading(true);
    try {
      const next = await uploadSessionCv(sessionId, file);
      setStatus(next);
      setReplacing(false);
    } catch (err: any) {
      setError(err.message || t("cv.errorUpload"));
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }, [sessionId, t]);

  const hasCv = !!status?.has_resume;
  const showDropzone = !hasCv || replacing;
  const summary = status?.summary;

  if (loading) {
    return (
      <div className="flex items-center justify-center gap-2 py-8 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> {t("cv.loading")}
      </div>
    );
  }

  // Not a B2B session (legacy / admin test-drive): nothing to gate on.
  if (status && !status.required) {
    return (
      <div className="space-y-4">
        <Button className="h-11 w-full lg:h-10" onClick={onContinue}>{continueLabel ?? t("cv.continue")}</Button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="space-y-1">
        <h2 className="text-lg font-semibold text-foreground">{t("cv.title")}</h2>
        <p className="text-sm text-muted-foreground">{t("cv.description")}</p>
      </div>

      {error && (
        <div className="bg-destructive/10 border border-destructive/20 text-destructive p-3 rounded-md text-sm">
          {error}
        </div>
      )}

      {hasCv && !replacing && (
        <div className="rounded-md border border-border bg-muted/30 p-4 space-y-3">
          <div className="flex items-start gap-3">
            <FileText className="h-5 w-5 text-primary shrink-0 mt-0.5" />
            <div className="min-w-0 flex-1 space-y-1">
              <p className="text-sm font-medium text-foreground truncate">{status?.original_filename ?? t("cv.existingFile")}</p>
              <p className="text-xs text-muted-foreground">{t("cv.whatWeRead")}</p>
              <ul className="text-sm text-foreground space-y-0.5">
                <li>
                  <span className="text-muted-foreground">{t("cv.summaryTitle")}: </span>
                  {summary?.professional_title || t("cv.summaryUnknown")}
                </li>
                <li>
                  <span className="text-muted-foreground">{t("cv.summaryYears")}: </span>
                  {summary?.years_of_experience != null ? summary.years_of_experience : t("cv.summaryUnknown")}
                </li>
                <li>
                  <span className="text-muted-foreground">{t("cv.summarySkills")}: </span>
                  {summary?.skills?.length ? summary.skills.join(", ") : t("cv.summaryUnknown")}
                </li>
              </ul>
              {status?.extraction_status !== "COMPLETED" && (
                <p className="text-xs text-amber-600">{t("cv.parseIncomplete")}</p>
              )}
            </div>
          </div>
          <div className="flex flex-col sm:flex-row gap-2">
            <Button className="h-11 flex-1 lg:h-10" onClick={onContinue} disabled={uploading}>
              {continueLabel ?? t("cv.useThisCv")}
            </Button>
            <Button variant="outline" className="h-11 flex-1 lg:h-10" onClick={() => setReplacing(true)} disabled={uploading}>
              <RefreshCw className="h-4 w-4 me-2" /> {t("cv.replace")}
            </Button>
          </div>
        </div>
      )}

      {showDropzone && (
        <div className="space-y-3">
          <label
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => { e.preventDefault(); setDragOver(false); void handleFile(e.dataTransfer.files?.[0]); }}
            className={[
              "flex flex-col items-center justify-center gap-2 rounded-md border-2 border-dashed p-6 text-center cursor-pointer transition-colors",
              dragOver ? "border-primary bg-primary/5" : "border-input hover:border-primary/50 hover:bg-muted/40",
              uploading ? "opacity-60 pointer-events-none" : "",
            ].join(" ")}
          >
            <input
              ref={inputRef}
              type="file"
              accept="application/pdf,.pdf"
              className="hidden"
              disabled={uploading}
              onChange={(e) => void handleFile(e.target.files?.[0])}
            />
            {uploading ? (
              <>
                <Loader2 className="h-6 w-6 animate-spin text-primary" />
                <p className="text-sm font-medium text-foreground">{t("cv.uploading")}</p>
                <p className="text-xs text-muted-foreground">{t("cv.uploadingHint")}</p>
              </>
            ) : (
              <>
                <UploadCloud className="h-6 w-6 text-primary" />
                <p className="text-sm font-medium text-foreground">{t("cv.dropHere")}</p>
                <p className="text-xs text-muted-foreground">{t("cv.constraints")}</p>
              </>
            )}
          </label>
          {replacing && !uploading && (
            <Button variant="ghost" className="h-11 w-full lg:h-10" onClick={() => { setReplacing(false); setError(""); }}>
              {t("cv.keepExisting")}
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
