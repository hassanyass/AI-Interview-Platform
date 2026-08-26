/**
 * WaitingRoomScreen — WR-D
 *
 * Candidate-visible screen rendered when phase === "WAITING_ROOM".
 * The interview clock is paused (backend sends time_remaining_seconds: null).
 * The only ways out are:
 *   1. Candidate clicks "Continue" -> PROCEED_TO_NEXT_SECTION sent via data channel
 *   2. Auto-timeout fires on the backend (voice_adapter.py) — no frontend timer shown
 *      to avoid pressure UX, per "free time" decision in CURRENT_DECISIONS.md.
 *
 * Himma design system (rebrand-architecture.md RB-B tokens) — uses the same
 * CSS vars and component palette as the rest of the interview workspace.
 */
import { useState } from "react";
import { CheckCircle2, Clock, ArrowRight, Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";

interface WaitingRoomScreenProps {
  /** 1-based index of the section that just finished */
  completedSectionIndex: number;
  totalSections: number;
  completedSectionType: string | null;
  nextSectionType: string | null;
  onContinue: () => void;
}

export function WaitingRoomScreen({
  completedSectionIndex,
  totalSections,
  completedSectionType,
  nextSectionType,
  onContinue,
}: WaitingRoomScreenProps) {
  const { t } = useTranslation();
  const [isContinuing, setIsContinuing] = useState(false);

  const handleContinue = () => {
    if (isContinuing) return;
    setIsContinuing(true);
    onContinue();
  };

  const labelFor = (type: string | null) =>
    type
      ? (t(`workspace.sectionTypes.${type}`, { defaultValue: type }) as string)
      : "";

  const isLastSection = !nextSectionType || completedSectionIndex >= totalSections;

  return (
    <div className="flex-1 flex flex-col items-center justify-center p-6 sm:p-10 bg-background">
      <div className="w-full max-w-lg">
        {/* Progress pill */}
        <div className="mb-8 flex items-center justify-center">
          <span className="inline-flex items-center gap-2 rounded-full border border-primary/20 bg-primary/8 px-4 py-1.5 text-xs font-semibold tracking-wide text-primary">
            {t("waitingRoom.progressLabel", {
              current: completedSectionIndex,
              total: totalSections,
            })}
          </span>
        </div>

        {/* Card */}
        <div className="rounded-2xl border border-border bg-card shadow-sm overflow-hidden">
          {/* Gradient header strip */}
          <div className="h-1.5 w-full bg-gradient-to-r from-primary/60 via-primary to-primary/60" />

          <div className="px-8 py-10 text-center">
            {/* Check icon */}
            <div className="mb-6 flex justify-center">
              <span className="flex h-16 w-16 items-center justify-center rounded-2xl bg-green-50 text-green-600">
                <CheckCircle2 className="h-8 w-8" />
              </span>
            </div>

            {/* Heading */}
            <h1 className="mb-2 text-2xl font-bold tracking-tight text-foreground">
              {t("waitingRoom.title")}
            </h1>
            <p className="mb-1 text-sm font-medium text-primary">
              {t("waitingRoom.subtitle")}
            </p>

            {/* Description */}
            <p className="mx-auto mb-8 max-w-sm text-sm leading-6 text-muted-foreground">
              {isLastSection
                ? t("waitingRoom.descLast")
                : t("waitingRoom.descWithNext", {
                    sectionType: labelFor(completedSectionType),
                    nextType: labelFor(nextSectionType),
                  })}
            </p>

            {/* Free-time notice */}
            <div className="mb-8 flex items-start gap-3 rounded-xl border border-blue-100 bg-blue-50/60 px-4 py-3 text-start">
              <Clock className="mt-0.5 h-4 w-4 shrink-0 text-blue-500" />
              <p className="text-xs leading-5 text-blue-700">
                {t("waitingRoom.timeNote")}
                {" "}
                <span className="text-blue-500/80">{t("waitingRoom.autoAdvance")}</span>
              </p>
            </div>

            {/* CTA */}
            {!isLastSection && (
              <button
                id="waiting-room-continue-btn"
                onClick={handleContinue}
                disabled={isContinuing}
                className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-primary px-6 py-3.5 text-sm font-semibold text-primary-foreground shadow-sm transition-all hover:bg-primary/90 hover:shadow-md hover:-translate-y-px active:translate-y-0 disabled:opacity-60 disabled:cursor-not-allowed disabled:translate-y-0"
              >
                {isContinuing ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <>
                    {t("waitingRoom.continueButton")}
                    <ArrowRight className="h-4 w-4" />
                  </>
                )}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
