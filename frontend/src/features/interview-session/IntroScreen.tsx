import { useState } from "react";
import { Info, ListChecks, Loader2, LogOut, PlayCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
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
        <div className="mx-auto flex h-16 max-w-[1440px] items-center justify-between px-4 sm:px-8">
          <div className="flex items-center gap-2 font-bold text-xl tracking-tight text-primary">
            <span dir="ltr" className="inline-block">e&</span> <span className="text-muted-foreground font-normal">|</span> هِمّة
          </div>
          <LanguageToggle />
        </div>
      </header>

      <main className="flex-1 flex flex-col items-center justify-center px-4 py-12">
        <div className="w-full max-w-4xl animate-in fade-in slide-in-from-bottom-4 duration-700 ease-out">
          
          <div className="text-center mb-12">
            <h1 className="text-4xl sm:text-5xl font-bold tracking-tight text-foreground px-4 mb-4 leading-[1.15]">
              {t("intro.title", { role })}
            </h1>
            <p className="text-lg text-muted-foreground max-w-xl mx-auto">
              {t("intro.subtitle")}
            </p>
          </div>

          {error && (
            <div className="bg-destructive/10 border border-destructive/20 text-destructive p-3 rounded-md text-sm text-center mb-8 max-w-2xl mx-auto" role="alert">
              {error}
            </div>
          )}

          <div className="grid gap-6 lg:grid-cols-5 mb-12">
            {/* Instructions Block - 3 columns on large screens */}
            <div className="lg:col-span-3 rounded-[24px] bg-white p-8 sm:p-10 shadow-xl shadow-black/5 flex flex-col justify-center">
              <div className="mb-6">
                <h3 className="font-bold text-foreground text-xl tracking-tight">{t("intro.instructionsLabel")}</h3>
                <div className="h-1 w-12 bg-primary mt-4 rounded-full"></div>
              </div>
              <p className="text-base sm:text-lg leading-relaxed text-muted-foreground">
                {candidateInstructions || t("intro.defaultInstructions")}
              </p>
            </div>

            {/* Rules & Setup Block - 2 columns on large screens, Premium Maroon */}
            <div className="lg:col-span-2 rounded-[24px] bg-[#4B0F1E] p-8 sm:p-10 shadow-xl shadow-[#4B0F1E]/20 flex flex-col">
              <div className="mb-8">
                <h3 className="font-bold text-white text-xl tracking-tight">{t("intro.rulesTitle")}</h3>
              </div>
              <ul className="space-y-6 text-base text-white/80 flex-1">
                <li className="flex items-start gap-4">
                  <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-white/10 text-xs font-bold text-white mt-0.5">1</span>
                  <span className="leading-relaxed">{t("intro.rule1")}</span>
                </li>
                <li className="flex items-start gap-4">
                  <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-white/10 text-xs font-bold text-white mt-0.5">2</span>
                  <span className="leading-relaxed">{t("intro.rule2")}</span>
                </li>
                <li className="flex items-start gap-4">
                  <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-white/10 text-xs font-bold text-white mt-0.5">3</span>
                  <span className="leading-relaxed">{t("intro.rule3")}</span>
                </li>
              </ul>
            </div>
          </div>

          <div className="flex flex-col items-center gap-5">
            <button
              onClick={onStart}
              disabled={isStarting || isEnding}
              className="inline-flex w-full sm:w-auto min-w-[280px] items-center justify-center gap-3 rounded-xl bg-primary px-10 py-4 text-base font-semibold text-primary-foreground shadow-lg shadow-primary/25 transition-all hover:bg-primary/90 hover:shadow-xl hover:shadow-primary/20 hover:-translate-y-1 active:translate-y-0 disabled:opacity-60 disabled:cursor-not-allowed disabled:hover:translate-y-0 disabled:hover:shadow-lg"
            >
              {isStarting ? <Loader2 className="h-5 w-5 animate-spin" /> : <PlayCircle className="h-5 w-5" />}
              {isStarting ? t("intro.starting") : t("intro.startButton")}
            </button>

            <button
              type="button"
              onClick={() => setIsEndDialogOpen(true)}
              disabled={isStarting || isEnding}
              className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground transition hover:text-destructive disabled:opacity-50"
            >
              {isEnding ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <LogOut className="h-3.5 w-3.5" />}
              {isEnding ? t("intro.ending") : t("intro.endLink")}
            </button>
          </div>
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
