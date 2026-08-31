import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import {
  getApplyContext,
  registerApplicant,
  type PublicApplyContext,
} from "../services/api/publicApply";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { LanguageToggle } from "../components/ui/LanguageToggle";
import { useTranslation } from "react-i18next";

type Step = "loading" | "invalid" | "form" | "registering";

export default function ApplyPage() {
  const { t } = useTranslation();
  const { token } = useParams<{ token: string }>();
  const navigate = useNavigate();
  const { setGuestSession } = useAuth();

  const [step, setStep] = useState<Step>("loading");
  const [context, setContext] = useState<PublicApplyContext | null>(null);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!token) return;
    getApplyContext(token)
      .then((data) => {
        setContext(data);
        setStep("form");
      })
      .catch(() => setStep("invalid"));
  }, [token]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) return;
    setSubmitting(true);
    setError("");
    setStep("registering");
    try {
      const result = await registerApplicant(token, { name, email });
      setGuestSession(result.access_token, result.session.id);
      navigate(`/interviews/${result.session.id}`);
    } catch (err: any) {
      setError(err.message || t('apply.failedToRegister'));
      setStep("form");
    } finally {
      setSubmitting(false);
    }
  };

  if (step === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background text-muted-foreground">
        {t('invite.loading')}
      </div>
    );
  }

  if (step === "invalid") {
    return (
      <div className="flex h-screen items-center justify-center px-4">
        <div className="max-w-md text-center space-y-2">
          <h1 className="text-xl font-semibold">{t('apply.invalidTitle')}</h1>
          <p className="text-muted-foreground text-sm">
            {t('apply.invalidDesc')}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col bg-background">
      {/* Himma / e& Header Lockup */}
      <header className="border-b bg-white">
        <div className="mx-auto flex h-16 max-w-5xl items-center justify-between px-4 sm:px-6">
          <div className="flex items-center gap-2 font-bold text-xl tracking-tight text-primary">
            <span dir="ltr" className="inline-block">e&</span> <span className="text-muted-foreground font-normal">|</span> هِمّة
          </div>
          <LanguageToggle />
        </div>
      </header>

      <main className="flex-1 flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-lg space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-700 ease-out">
          <div className="text-center space-y-4 px-4">
            <h1 className="text-3xl sm:text-4xl font-bold tracking-tight text-foreground leading-tight">
              {context?.job_title}
            </h1>
            
            {(context?.seniority || context?.job_description) && (
              <div className="space-y-2 max-w-md mx-auto">
                {context?.seniority && (
                  <p className="text-sm font-semibold text-primary uppercase tracking-wider">
                    {context.seniority}
                  </p>
                )}
                {context?.job_description && (
                  <p className="text-muted-foreground">
                    {context.job_description}
                  </p>
                )}
              </div>
            )}

            {context?.candidate_instructions && (
              <p className="text-sm text-muted-foreground max-w-md mx-auto italic">
                "{context.candidate_instructions}"
              </p>
            )}

            {context?.duration_minutes && (
              <div className="inline-flex bg-muted/50 px-4 py-2 rounded-full border border-muted mt-2">
                <p className="text-sm text-muted-foreground font-medium flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full bg-primary/60"></span>
                  {t('invite.estDuration', { minutes: context.duration_minutes })}
                </p>
              </div>
            )}
          </div>

          <Card className="shadow-xl shadow-black/5 border-muted/60">
            <CardContent className="p-6 space-y-4">
              {error && (
                <div className="bg-destructive/10 border border-destructive/20 text-destructive p-3 rounded-md text-sm">
                  {error}
                </div>
              )}

              {step === "registering" ? (
                <div className="flex flex-col items-center justify-center py-8 space-y-4 animate-in fade-in zoom-in-95 duration-500">
                  <div className="h-8 w-8 rounded-full border-4 border-primary/20 border-t-primary animate-spin" />
                  <p className="text-sm font-medium text-muted-foreground">{t('invite.starting')}</p>
                </div>
              ) : (
                <form onSubmit={handleSubmit} className="space-y-4 animate-in fade-in duration-300">
                  <div className="space-y-2">
                    <label className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70">
                      {t('apply.fullName')}
                    </label>
                    <input
                      required
                      type="text"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                    />
                  </div>
                  <div className="space-y-2">
                    <label className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70">
                      {t('invite.emailLabel')}
                    </label>
                    <input
                      required
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                    />
                  </div>
                  {/* CV upload deliberately deferred — see docs/CURRENT_DECISIONS.md /
                      Sub-phase 6C's resume_id: Optional field, added later once the
                      upload-sequencing question is resolved. */}
                  <Button
                    type="submit"
                    className="w-full"
                    disabled={submitting}
                  >
                    {submitting ? t('apply.submitting') : t('apply.continue')}
                  </Button>
                </form>
              )}
            </CardContent>
          </Card>
        </div>
      </main>
    </div>
  );
}
