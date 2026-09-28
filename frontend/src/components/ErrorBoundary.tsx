import React from "react";
import { withTranslation, type WithTranslation } from "react-i18next";

interface Props extends WithTranslation {
  /** "page" = full-page fallback; "interview" = candidate-facing copy that says progress is saved. */
  variant?: "page" | "interview";
  children: React.ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * H2-E: a render/lifecycle throw used to white-screen the whole app --
 * including a candidate mid-interview. This catches it, shows a short
 * explanation and a reload button, and logs the error. Two copies: the
 * generic page one, and the interview one that says the backend has the
 * progress (it checkpoints every turn; reconnect resumes).
 */
class ErrorBoundaryImpl extends React.Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error("[ErrorBoundary]", error, info.componentStack);
  }

  render() {
    const { t, variant = "page", children } = this.props;
    const { error } = this.state;
    if (!error) return children;
    const interview = variant === "interview";
    return (
      <main role="alert" className="min-h-dvh bg-background text-foreground flex items-center justify-center p-6">
        <div className="w-full max-w-lg rounded-2xl border border-border bg-card p-6 shadow-sm">
          <h1 className="text-xl font-semibold">{t(interview ? "errorBoundary.interviewTitle" : "errorBoundary.title")}</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            {t(interview ? "errorBoundary.interviewBody" : "errorBoundary.body")}
          </p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="mt-4 inline-flex h-11 items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground"
          >
            {t("errorBoundary.reload")}
          </button>
          <details className="mt-4 text-xs text-muted-foreground">
            <summary>{t("errorBoundary.details")}</summary>
            <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap font-mono">{String(error?.stack || error)}</pre>
          </details>
        </div>
      </main>
    );
  }
}

export const ErrorBoundary = withTranslation()(ErrorBoundaryImpl);
