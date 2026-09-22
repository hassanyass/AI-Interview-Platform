/**
 * Rendered by main.tsx instead of the app when src/config.ts reports
 * problems. Operator-facing (the person deploying the build), so plain
 * English and no dependency on i18n, auth or the API — none of those can be
 * trusted to work when the configuration is broken.
 */
export function ConfigErrorScreen({ problems }: { problems: readonly string[] }) {
  return (
    <main
      dir="ltr"
      className="min-h-dvh bg-background text-foreground flex items-center justify-center p-6"
      role="alert"
    >
      <div className="w-full max-w-lg rounded-2xl border border-border bg-card p-6 shadow-sm">
        <h1 className="text-xl font-semibold">Configuration error</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          This build cannot start because required environment variables are missing or invalid.
          Set them in <code className="font-mono">frontend/.env</code> (see{" "}
          <code className="font-mono">frontend/.env.example</code>) and rebuild.
        </p>
        <ul className="mt-4 space-y-1 text-sm font-mono">
          {problems.map((p) => (
            <li key={p} className="rounded-md bg-muted px-3 py-2">
              {p}
            </li>
          ))}
        </ul>
      </div>
    </main>
  );
}
