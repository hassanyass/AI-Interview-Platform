import { useState } from "react";
import { ArrowRight, Loader2 } from "lucide-react";
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
    <div className="flex flex-col items-center justify-center p-6 sm:p-10 w-full min-h-[60vh] bg-transparent">
      <div className="w-full max-w-2xl text-center space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-700 ease-out">
        
        {/* Eyebrow Label */}
        <div className="inline-flex justify-center">
          <span className="text-xs font-semibold uppercase tracking-[0.2em] text-primary/80">
            {t("waitingRoom.progressLabel", {
              current: completedSectionIndex,
              total: totalSections,
            })}
          </span>
        </div>

        {/* Headline */}
        <h1 className="text-4xl sm:text-5xl font-bold tracking-tight text-foreground px-4 leading-[1.15]">
          {t("waitingRoom.title")}
        </h1>
        
        {/* Supporting text */}
        <p className="mx-auto max-w-xl text-lg text-muted-foreground leading-relaxed">
          {isLastSection
            ? t("waitingRoom.descLast")
            : t("waitingRoom.descWithNext", {
                sectionType: labelFor(completedSectionType),
                nextType: labelFor(nextSectionType),
              })}
        </p>

        {/* Free-time subtle notice */}
        <div className="pt-2">
          <p className="text-sm font-medium text-muted-foreground/60">
            {t("waitingRoom.timeNote")}{" "}
            <span className="text-muted-foreground/90">{t("waitingRoom.autoAdvance")}</span>
          </p>
        </div>

        {/* Primary CTA */}
        {!isLastSection && (
          <div className="pt-8 flex justify-center">
            <button
              id="waiting-room-continue-btn"
              onClick={handleContinue}
              disabled={isContinuing}
              className="inline-flex items-center justify-center gap-3 rounded-xl bg-primary px-10 py-4 text-base font-semibold text-primary-foreground shadow-lg shadow-primary/25 transition-all hover:bg-primary/90 hover:shadow-xl hover:shadow-primary/20 hover:-translate-y-1 active:translate-y-0 disabled:opacity-60 disabled:cursor-not-allowed disabled:hover:translate-y-0 disabled:hover:shadow-lg"
            >
              {isContinuing ? (
                <Loader2 className="h-5 w-5 animate-spin" />
              ) : (
                <>
                  {t("waitingRoom.continueButton")}
                  <ArrowRight className="h-5 w-5" />
                </>
              )}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
