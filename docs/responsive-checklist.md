# Responsive phase — verify checklist

Copy this block into the Verify section of every responsive phase
(`docs/responsive-design-plan.md` §4). One block per surface touched.
Tick only what was actually observed; attach the harness output.

```
Surface: <route or component>          Phase: R<n>
Harness: `npm run responsive -- --routes=<route>`  → report.json attached / linked

Matrix (phone-s 360, phone 375, phone-land 812×375, tablet 768, tablet-land 1024, laptop 1280, desktop 1440)
                          LTR                      RTL
                          ok / notes               ok / notes
phone-s                   [ ]                      [ ]
phone                     [ ]                      [ ]
phone-land                [ ]                      [ ]
tablet                    [ ]                      [ ]
tablet-land               [ ]                      [ ]
laptop                    [ ]                      [ ]
desktop                   [ ]                      [ ]

Per matrix entry:
[ ] no horizontal scroll        (report: overflow=false)
[ ] every desktop action reachable (report: hiddenControls empty, or each one has a visible replacement)
[ ] touch targets >= 44px on touch widths (report: smallTargets empty, or each one justified)
[ ] no clipped/overlapping text; no truncated DATA (titles may truncate with a tooltip)
[ ] fixed/sticky bars cover nothing; safe-area respected (pb-[var(--safe-bottom)] on bottom bars)
[ ] dvh not vh for full-height layouts
[ ] logical properties only (ps/pe/ms/me/start/end/text-start/text-end) — no left/right/pl/pr/text-left/text-right
[ ] icon-only controls have aria-label; focus order sensible

Commands (paste output):
  npm run typecheck
  npx oxlint src
  npm test

R6 only — real devices:
  device / browser / what was exercised / result
```

## Reading the harness report

`frontend/.responsive/report.json` has one entry per shot:

| field | meaning |
|---|---|
| `overflow` | `scrollWidth > innerWidth` — horizontal page scroll exists. Always a defect. |
| `overflowers` | first 8 elements whose right edge passes the viewport — where to look. |
| `smallTargets` | interactive elements under 44×44 on touch viewports. Justify or fix. |
| `hiddenControls` | buttons/links in the DOM with `display:none` — the `hidden sm:flex` pattern. Each needs a visible replacement at that width or it is a P0. |
| `error` | navigation failed (route needs auth / server down). |

`--strict` makes the script exit 1 on any overflow or error, for CI later.
