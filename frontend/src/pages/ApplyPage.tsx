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
            e& <span className="text-muted-foreground font-normal">|</span> هِمّة
          </div>
          <LanguageToggle />
        </div>
      </header>

      <main className="flex-1 flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-lg space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-2xl">{context?.job_title}</CardTitle>
              {context?.seniority && (
                <CardDescription className="text-base">{context.seniority}</CardDescription>
              )}
            </CardHeader>
            <CardContent className="space-y-4">
              {context?.job_description && (
                <p className="text-sm text-foreground">{context.job_description}</p>
              )}
              {context?.candidate_instructions && (
                <div className="border-t pt-4 mt-2">
                  <h4 className="text-sm font-semibold mb-1">{t('invite.instructions')}</h4>
                  <p className="text-sm text-muted-foreground">
                    {context.candidate_instructions}
                  </p>
                </div>
              )}
              <div className="bg-secondary/10 p-3 rounded-md border border-secondary/20">
                <p className="text-sm text-secondary-foreground font-medium">
                  {t('invite.estDuration', { minutes: context?.duration_minutes })}
                </p>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-6 space-y-4">
              {error && (
                <div className="bg-destructive/10 border border-destructive/20 text-destructive p-3 rounded-md text-sm">
                  {error}
                </div>
              )}

              <form onSubmit={handleSubmit} className="space-y-4">
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
                  disabled={submitting || step === "registering"}
                >
                  {step === "registering" ? t('invite.starting') : submitting ? t('apply.submitting') : t('apply.continue')}
                </Button>
              </form>
            </CardContent>
          </Card>
        </div>
      </main>
    </div>
  );
}
