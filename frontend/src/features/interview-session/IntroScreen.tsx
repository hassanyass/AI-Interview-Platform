import { useState } from "react";
import { Loader2, LogOut, PlayCircle, Shield, CheckCircle2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { LanguageToggle } from "../../components/ui/LanguageToggle";
import { EndInterviewDialog } from "./EndInterviewDialog";
import { DevicePreview } from "./DevicePreview";

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
  // PR-A: explicit, affirmative consent required before Start Session is
  // even clickable — not implied by continuing. Unchecked by default.
  const [hasConsented, setHasConsented] = useState(false);
  const [isDeviceReady, setIsDeviceReady] = useState(false);

  const handleConfirmEnd = () => {
    setIsEndDialogOpen(false);
    onEnd();
  };

  const canStart = hasConsented && isDeviceReady && !isStarting && !isEnding;

  return (
    <div className="min-h-screen flex flex-col bg-[#F8F7F4]">
      {/* Header */}
      <header className="border-b bg-white/80 backdrop-blur-sm sticky top-0 z-10">
        <div className="mx-auto flex h-16 max-w-5xl items-center justify-between px-4 sm:px-8">
          <div className="flex items-center gap-2 font-bold text-xl tracking-tight text-primary">
            <span dir="ltr" className="inline-block">e&</span>{" "}
            <span className="text-muted-foreground font-normal">|</span> هِمّة
          </div>
          <LanguageToggle />
        </div>
      </header>

      <main className="flex-1 flex flex-col items-center px-4 py-10 sm:py-14">
        <div className="w-full max-w-5xl animate-in fade-in slide-in-from-bottom-4 duration-700 ease-out space-y-8">

          {/* ── Page heading ── */}
          <div className="text-center">
            <h1 className="text-3xl sm:text-4xl font-bold tracking-tight text-slate-900 mb-2">
              {t("intro.title", { role })}
            </h1>
            <p className="text-base text-slate-500 max-w-lg mx-auto">
              {t("intro.subtitle")}
            </p>
          </div>

          {/* ── Inline error ── */}
          {error && (
            <div
              className="rounded-xl bg-red-50 border border-red-200 text-red-700 p-4 text-sm text-center"
              role="alert"
            >
              {error}
            </div>
          )}

          {/* ── Row 1: Instructions + Rules (2-col) ── */}
          <div className="grid gap-4 sm:grid-cols-[1fr_auto]">
            {/* Instructions — wider */}
            <div className="rounded-2xl bg-white border border-slate-200 p-6 sm:p-8 shadow-sm">
              <h2 className="font-bold text-slate-900 text-base mb-1">
                {t("intro.instructionsLabel")}
              </h2>
              <div className="h-0.5 w-8 bg-primary rounded-full mb-4" />
              <p className="text-sm sm:text-base leading-relaxed text-slate-600">
                {candidateInstructions || t("intro.defaultInstructions")}
              </p>
            </div>

            {/* Rules — fixed width pill */}
            <div className="rounded-2xl bg-[#4B0F1E] p-6 shadow-sm sm:w-64 flex flex-col">
              <h2 className="font-bold text-white text-base mb-4">
                {t("intro.rulesTitle")}
              </h2>
              <ul className="space-y-4 flex-1">
                {[t("intro.rule1"), t("intro.rule2"), t("intro.rule3")].map((rule, i) => (
                  <li key={i} className="flex items-start gap-3">
                    <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-white/15 text-[11px] font-bold text-white mt-0.5">
                      {i + 1}
                    </span>
                    <span className="text-sm leading-relaxed text-white/80">{rule}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>

          {/* ── Row 2: Device check — full-width card ── */}
          <div className="rounded-2xl bg-white border border-slate-200 p-6 sm:p-8 shadow-sm">
            <h2 className="font-bold text-slate-900 text-base mb-1">
              Camera &amp; Microphone Check
            </h2>
            <p className="text-xs text-slate-500 mb-5">
              Confirm your devices are working before you begin.
            </p>
            <DevicePreview onReady={(hasCamera, hasMic) => setIsDeviceReady(true)} />
          </div>

          {/* ── Row 3: Consent + Start — full-width card ── */}
          {/* PR-A: recording/monitoring consent — plain-language disclosure
              of exactly what's captured (docs/proctoring-architecture.md).
              Start Session stays disabled until checked. */}
          <div className="rounded-2xl bg-white border border-slate-200 p-6 sm:p-8 shadow-sm">
            <div className="flex items-start gap-4 mb-6">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10">
                <Shield className="h-5 w-5 text-primary" />
              </div>
              <div>
                <h2 className="font-bold text-slate-900 text-base mb-1">
                  {t("intro.consent.title")}
                </h2>
                <p className="text-sm leading-relaxed text-slate-500">
                  {t("intro.consent.body")}
                </p>
              </div>
            </div>

            {/* Consent checkbox */}
            <label className="flex items-start gap-3 cursor-pointer select-none rounded-xl border border-slate-200 bg-slate-50 p-4 hover:bg-slate-100 transition-colors mb-6">
              <input
                type="checkbox"
                id="consent-checkbox"
                checked={hasConsented}
                onChange={(e) => setHasConsented(e.target.checked)}
                className="mt-0.5 h-4 w-4 shrink-0 rounded border-slate-400 text-primary focus:ring-primary"
              />
              <span className="text-sm font-medium text-slate-800">
                {t("intro.consent.checkboxLabel")}
              </span>
            </label>

            {/* Readiness summary */}
            <div className="flex flex-wrap items-center gap-3 mb-6 text-xs text-slate-500">
              <div className={`flex items-center gap-1.5 ${isDeviceReady ? "text-emerald-600" : "text-slate-400"}`}>
                <CheckCircle2 className="h-3.5 w-3.5" />
                Devices checked
              </div>
              <div className={`flex items-center gap-1.5 ${hasConsented ? "text-emerald-600" : "text-slate-400"}`}>
                <CheckCircle2 className="h-3.5 w-3.5" />
                Consent given
              </div>
            </div>

            {/* CTA row */}
            <div className="flex flex-col sm:flex-row items-center gap-4">
              <button
                id="start-session-btn"
                onClick={onStart}
                disabled={!canStart}
                className="inline-flex w-full sm:w-auto min-w-[220px] items-center justify-center gap-2.5 rounded-xl bg-primary px-8 py-3.5 text-sm font-semibold text-primary-foreground shadow-md shadow-primary/20 transition-all hover:bg-primary/90 hover:shadow-lg hover:shadow-primary/20 hover:-translate-y-0.5 active:translate-y-0 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:translate-y-0 disabled:hover:shadow-md"
              >
                {isStarting ? <Loader2 className="h-4 w-4 animate-spin" /> : <PlayCircle className="h-4 w-4" />}
                {isStarting ? t("intro.starting") : t("intro.startButton")}
              </button>

              <button
                type="button"
                onClick={() => setIsEndDialogOpen(true)}
                disabled={isStarting || isEnding}
                className="flex items-center gap-1.5 text-xs font-medium text-slate-400 transition hover:text-red-500 disabled:opacity-50"
              >
                {isEnding ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <LogOut className="h-3.5 w-3.5" />}
                {isEnding ? t("intro.ending") : t("intro.endLink")}
              </button>
            </div>
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
