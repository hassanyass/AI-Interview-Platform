import { useTranslation } from "react-i18next";
import { LanguageToggle } from "../../components/ui/LanguageToggle";
import { FinalResult } from "../results/FinalResult";
import type { InterviewSessionResponse } from "../../types/api";

/**
 * SessionEndedScreen — Plan 11's real closing/thank-you screen chrome
 * (header + FinalResult card). Extracted verbatim from InterviewWorkspace's
 * `isCompleted` branch (no visual/behavioral change) so a second entry
 * point — resuming directly into an already-COMPLETED session, which never
 * mounts InterviewWorkspace/LiveKitRoom at all — can render the exact same
 * screen instead of either duplicating this markup or (the pre-fix bug)
 * navigating to a route that doesn't exist. InterviewWorkspace still owns
 * this markup for the live-completion path; this component is the single
 * shared source for both.
 */
interface SessionEndedScreenProps {
  session: InterviewSessionResponse;
}

export function SessionEndedScreen({ session }: SessionEndedScreenProps) {
  const { t } = useTranslation();

  return (
    <div className="min-h-screen w-full bg-background text-foreground flex flex-col">
      <header className="border-b bg-white">
        <div className="mx-auto flex min-h-16 max-w-[1440px] items-center justify-between gap-4 px-4 py-3 sm:px-8">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex items-center gap-2 font-bold text-xl tracking-tight text-primary hidden sm:flex">
              <span dir="ltr" className="inline-block">e&</span> <span className="text-muted-foreground font-normal">|</span> هِمّة
            </div>
            <div className="min-w-0 sm:ms-4 sm:ps-4 sm:border-s">
              <p className="truncate text-sm font-semibold text-foreground">{session.role || t('workspace.session')}</p>
              <p className="text-xs text-muted-foreground">{t('workspace.sessionEnded')}</p>
            </div>
          </div>
          <div className="flex items-center gap-4 text-xs text-muted-foreground sm:gap-6">
            <LanguageToggle />
            <span className="hidden items-center gap-2 sm:flex">
              <span className="h-2 w-2 rounded-full bg-muted-foreground" />
              {t('workspace.sessionEnded')}
            </span>
          </div>
        </div>
      </header>
      <FinalResult session={session} />
    </div>
  );
}
