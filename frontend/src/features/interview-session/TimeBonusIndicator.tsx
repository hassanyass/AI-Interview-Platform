import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

/**
 * Verbal-flow orchestration (docs/verbal-section-flow-plan.md, B4): renders
 * the interview clock digits plus the two signals a follow-up time grant
 * produces -- the MOMENT ("+2:00" rises in beside the digits, holds, fades;
 * the digits pulse once) and the running TALLY ("+4:00 added") that stays
 * while any time has been granted this section.
 *
 * Trigger: the running total (`time_bonus_total_seconds`) increasing.
 * Deliberately NOT the transient `time_bonus_granted_seconds` field alone --
 * the agent sends that on exactly one state update, but two updates in a
 * row could each carry the same value (two grants, no intervening update),
 * and a React effect keyed on an unchanged value would not re-fire. A
 * monotonically increasing total is unambiguous; `granted` is used only as
 * the preferred label amount when present.
 *
 * Colour: the positive signal uses the `secondary` (maroon) token -- the
 * e& grey/red/maroon palette -- not a green "success" flash. Motion is
 * gated on motion-safe: so prefers-reduced-motion users get the static
 * chip without the rise/pulse.
 */

const MOMENT_MS = 2600;

function formatBonus(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `+${m}:${String(s).padStart(2, "0")}`;
}

export function TimeBonusIndicator({
  formattedTime,
  grantedSeconds,
  totalSeconds,
}: {
  formattedTime: string;
  grantedSeconds?: number | null;
  totalSeconds?: number;
}) {
  const { t } = useTranslation();
  const total = totalSeconds ?? 0;
  const prevTotalRef = useRef(total);
  const [moment, setMoment] = useState<number | null>(null);

  useEffect(() => {
    const prev = prevTotalRef.current;
    prevTotalRef.current = total;
    if (total <= prev) return;
    const amount = grantedSeconds && grantedSeconds > 0 ? grantedSeconds : total - prev;
    setMoment(amount);
    const timer = window.setTimeout(() => setMoment(null), MOMENT_MS);
    return () => window.clearTimeout(timer);
  }, [total, grantedSeconds]);

  return (
    <span className="inline-flex items-center gap-2">
      <span className={moment != null ? "motion-safe:animate-pulse" : ""}>{formattedTime}</span>
      {moment != null && (
        <span
          key={total}
          role="status"
          aria-live="polite"
          className="rounded-full border border-secondary/25 bg-secondary/10 px-2 py-0.5 text-xs font-semibold text-secondary motion-safe:[animation:himma-bonus-rise_300ms_ease-out_both]"
        >
          {formatBonus(moment)}
        </span>
      )}
      {moment == null && total > 0 && (
        <span className="text-[11px] font-medium text-secondary/80" title={t("workspace.timeBonusTitle")}>
          {t("workspace.timeBonusAdded", { time: formatBonus(total) })}
        </span>
      )}
    </span>
  );
}
