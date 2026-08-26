/**
 * IntroScreen — post-registration greeting, shown once for a fresh
 * (status === "CREATED") session, before the LiveKit room is ever
 * connected. "Start Session" is what triggers the actual connect (see
 * InterviewSession.tsx) — nothing in voice_adapter.py/controller.py
 * changes, this purely delays when the frontend chooses to connect.
 *
 * Ending from here uses END_INTERVIEW's REST equivalent
 * (POST /interviews/{id}/terminate) rather than the data-channel
 * END_INTERVIEW candidate control, since no live session exists yet to
 * send it over. END_SECTION_EARLY is deliberately never used here — no
 * core section is active before Start Session.
 */
import { useState } from "react";
import { Info, ListChecks, Loader2, LogOut, Mic, PlayCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { LanguageToggle } from "../../components/ui/LanguageToggle";
import { EndInterviewDialog } from "./EndInterviewDialog";

interface IntroScreenProps {
  role: string;
  candidateInstructions?: string | null;
  onStart: () => void;
  onEnd: () => void;
  isStarting?: boolean;
  isEnding?: boolean;
  /** Inline, retry-in-place error — e.g. Start Session's token fetch
   *  failed. Shown on this screen rather than bouncing to a full-page
   *  error, since the candidate's context/instructions are still relevant
   *  and nothing has gone wrong with the session itself. */
  error?: string;
}

export function IntroScreen({
  role,
  candidateInstructions,
  onStart,
  onEnd,
  isStarting = false,
  isEnding = false,
  error,
}: IntroScreenProps) {
  const { t } = useTranslation();
  const [isEndDialogOpen, setIsEndDialogOpen] = useState(false);

  const handleConfirmEnd = () => {
    setIsEndDialogOpen(false);
    onEnd();
  };

  return (
    <div className="min-h-screen flex flex-col bg-background">
      <header className="border-b bg-white">
        <div className="mx-auto flex h-16 max-w-3xl items-center justify-between px-4 sm:px-6">
          <div className="flex items-center gap-2 font-bold text-xl tracking-tight text-primary">
            e& <span className="text-muted-foreground font-normal">|</span> هِمّة
          </div>
          <LanguageToggle />
        </div>
      </header>

      <main className="flex-1 flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-lg">
          <Card className="overflow-hidden">
            <div className="h-1.5 w-full bg-gradient-to-r from-primary/60 via-primary to-primary/60" />
            <CardHeader>
              <CardTitle className="text-2xl">{t("intro.title", { role })}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-5">
              <p className="text-sm leading-6 text-muted-foreground">{t("intro.subtitle")}</p>

              {error && (
                <div className="bg-destructive/10 border border-destructive/20 text-destructive p-3 rounded-md text-sm" role="alert">
                  {error}
                </div>
              )}

              {candidateInstructions && (
                <div className="flex items-start gap-3 rounded-xl border border-primary/15 bg-primary/5 px-4 py-3.5 text-start">
                  <Info className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                  <div>
                    <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-primary">
                      {t("intro.instructionsLabel")}
                    </p>
                    <p className="text-sm leading-6 text-foreground">{candidateInstructions}</p>
                  </div>
                </div>
              )}

              <ul className="space-y-2.5 text-sm text-muted-foreground">
                <li className="flex items-start gap-2.5">
                  <Mic className="mt-0.5 h-4 w-4 shrink-0 text-primary/70" />
                  {t("intro.tipMic")}
                </li>
                <li className="flex items-start gap-2.5">
                  <ListChecks className="mt-0.5 h-4 w-4 shrink-0 text-primary/70" />
                  {t("intro.tipSections")}
                </li>
              </ul>

              <Button size="lg" className="w-full gap-2" onClick={onStart} disabled={isStarting || isEnding}>
                {isStarting ? <Loader2 className="h-5 w-5 animate-spin" /> : <PlayCircle className="h-5 w-5" />}
                {isStarting ? t("intro.starting") : t("intro.startButton")}
              </Button>

              <button
                type="button"
                onClick={() => setIsEndDialogOpen(true)}
                disabled={isStarting || isEnding}
                className="mx-auto flex items-center gap-1.5 text-xs font-medium text-muted-foreground transition hover:text-destructive disabled:opacity-50"
              >
                {isEnding ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <LogOut className="h-3.5 w-3.5" />}
                {isEnding ? t("intro.ending") : t("intro.endLink")}
              </button>
            </CardContent>
          </Card>
        </div>
      </main>

      <EndInterviewDialog
        isOpen={isEndDialogOpen}
        variant="preStart"
        onCancel={() => setIsEndDialogOpen(false)}
        onConfirm={handleConfirmEnd}
      />
    </div>
  );
}
