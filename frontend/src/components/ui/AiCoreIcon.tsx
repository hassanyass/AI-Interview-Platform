/**
 * The e& brand guide's Section 12 ("AI Visual Language") explicitly rejects
 * the stereotypical robot-head/glowing-brain/circuit-board AI iconography
 * and instead recommends a simple circular motif with subtle motion:
 *   "A simple circular visual can represent the AI interviewer... use
 *    subtle motion around the circle during listening/speaking states."
 * Used wherever a number on these dashboards is an AI-DERIVED judgment
 * (a recommendation, a generated score) rather than a plain fact (a
 * count), so the two read as visually distinct without adding another
 * color to the palette -- the ring is the same maroon/secondary token
 * already used for "high-value summary" per the guide's own color table.
 */
export function AiCoreIcon({ className = "" }: { className?: string }) {
  return (
    <span className={`relative inline-flex h-4 w-4 shrink-0 items-center justify-center ${className}`} aria-hidden="true">
      <span className="absolute inline-flex h-full w-full rounded-full bg-secondary/30 animate-ping" style={{ animationDuration: "2.5s" }} />
      <span className="relative inline-flex h-full w-full rounded-full border-[1.5px] border-secondary" />
      <span className="absolute h-1.5 w-1.5 rounded-full bg-secondary" />
    </span>
  );
}
