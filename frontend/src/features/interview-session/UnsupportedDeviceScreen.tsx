import { Loader2, LogOut, Monitor } from "lucide-react";
import { useTranslation } from "react-i18next";
import { LanguageToggle } from "../../components/ui/LanguageToggle";

/**
 * Shown instead of the pre-flight screen when the device cannot take the
 * live interview — product decision D1 (docs/CURRENT_DECISIONS.md, "Device
 * support for the live interview"). The rule itself is in
 * `lib/deviceSupport.ts`; this file only says so kindly.
 *
 * Deliberately NOT an error screen. Nothing has gone wrong and nothing is
 * lost: the session exists, the candidate is simply on the wrong device and
 * the same link will work on a laptop. So it keeps the ordinary header and
 * language toggle, gives the reason in plain words, and offers no Start
 * button to press — which is the whole point of gating here rather than at
 * a fullscreen request that would fail after consent and camera access.
 */
export function UnsupportedDeviceScreen({
  onEnd,
  isEnding = false,
}: {
  onEnd: () => void;
  isEnding?: boolean;
}) {
  const { t } = useTranslation();

  return (
    <div className="min-h-dvh flex flex-col bg-[#F8F7F4]">
      <header className="border-b bg-white/80 backdrop-blur-sm">
        <div className="mx-auto flex h-16 max-w-5xl items-center justify-between px-4 sm:px-8">
          <div className="flex items-center gap-2 font-bold text-xl tracking-tight text-primary">
            <span dir="ltr" className="inline-block">e&</span>{" "}
            <span className="text-muted-foreground font-normal">|</span> هِمّة
          </div>
          <LanguageToggle />
        </div>
      </header>

      <main className="flex-1 flex items-center justify-center px-4 py-10">
        <div className="w-full max-w-lg rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary/10">
            <Monitor className="h-6 w-6 text-primary" />
          </div>

          <h1 className="mt-5 text-2xl font-bold tracking-tight text-slate-900">
            {t("intro.unsupported.title")}
          </h1>
          <p className="mt-3 text-sm leading-relaxed text-slate-600">
            {t("intro.unsupported.body")}
          </p>

          <p className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-4 text-xs leading-relaxed text-slate-500">
            {t("intro.unsupported.why")}
          </p>

          <p className="mt-4 text-xs font-medium text-slate-500">
            {t("intro.unsupported.linkHint")}
          </p>

          {/* No Start button by design. Ending is still offered, because a
              candidate who cannot continue should not be stuck here. */}
          <button
            type="button"
            onClick={onEnd}
            disabled={isEnding}
            className="mt-6 inline-flex min-h-11 items-center gap-1.5 px-2 text-xs font-medium text-slate-400 transition hover:text-red-500 disabled:opacity-50 lg:min-h-10"
          >
            {isEnding ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <LogOut className="h-3.5 w-3.5" />}
            {isEnding ? t("intro.ending") : t("intro.endLink")}
          </button>
        </div>
      </main>
    </div>
  );
}
