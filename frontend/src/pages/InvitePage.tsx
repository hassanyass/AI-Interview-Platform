import { useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { supabase } from "../lib/supabase";
import { useAuth } from "../context/AuthContext";
import {
  getInvitationContext,
  redeemInvitation,
  type InvitationPublicContext,
} from "../services/api/publicInvitations";
import { Card, CardContent } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { LanguageToggle } from "../components/ui/LanguageToggle";
import { useTranslation, Trans } from 'react-i18next';
import { CvUploadStep } from "../features/candidate-entry/CvUploadStep";

type Step = "loading" | "invalid" | "email" | "otp" | "redeeming" | "cv";

export default function InvitePage() {
  const { t } = useTranslation();
  const { token } = useParams<{ token: string }>();
  const navigate = useNavigate();
  const { session } = useAuth();

  const [step, setStep] = useState<Step>("loading");
  const [context, setContext] = useState<InvitationPublicContext | null>(null);
  const [email, setEmail] = useState("");
  const [otpCode, setOtpCode] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  // Guards against double-firing the redeem effect below (e.g. StrictMode's
  // double-invoke in dev, or `session` changing more than once).
  const hasRedeemedRef = useRef(false);
  const [sessionId, setSessionId] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    getInvitationContext(token)
      .then((data) => {
        setContext(data);
        // Pre-filled, not locked — the real boundary is the backend's
        // exact-match check against the verified OTP email, not this field.
        setEmail(data.candidate_email);
        setStep("email");
      })
      .catch(() => setStep("invalid"));
  }, [token]);

  const doRedeem = async () => {
    if (!token || hasRedeemedRef.current) return;
    hasRedeemedRef.current = true;
    setStep("redeeming");
    setError("");
    try {
      const redeemResult = await redeemInvitation(token);
      // Background subsection step 2 (ruling Q2): redeem -> mandatory CV ->
      // Start. An invitee whose application already carries a CV is offered
      // "use the CV we have" inside the step rather than forced to re-upload.
      setSessionId(redeemResult.session.id);
      setStep("cv");
    } catch (err: any) {
      hasRedeemedRef.current = false;
      setError(err.message || t('invite.failedToRedeem'));
      setStep("otp");
      setSubmitting(false);
    }
  };

  // Not every Supabase project's email template sends a typeable OTP code —
  // some (like this one, discovered during live verification) send a magic
  // link instead. The Supabase client auto-detects a session from the URL
  // when the candidate clicks that link and lands back on this page, which
  // AuthContext picks up via onAuthStateChange. Either path — a typed code
  // (handleVerifyOtp below) or a clicked magic link — ends here: as soon as
  // a real Supabase session exists while we're waiting on OTP, redeem.
  useEffect(() => {
    if (session && (step === "email" || step === "otp")) {
      doRedeem();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session, step]);

  const handleSendOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const { error: otpError } = await supabase.auth.signInWithOtp({
        email,
        options: {
          // Without this, Supabase's magic-link email redirects to the
          // project's default Site URL (the app root) instead of back to
          // this specific invite page — landing the candidate on their
          // normal dashboard instead of continuing the redeem flow. The
          // typed-code path doesn't need this (verifyOtp is called
          // directly, no redirect involved) but the link in the same
          // email does.
          emailRedirectTo: window.location.href,
        },
      });
      if (otpError) throw otpError;
      setStep("otp");
    } catch (err: any) {
      setError(err.message || t('invite.failedToSend'));
    } finally {
      setSubmitting(false);
    }
  };

  const handleVerifyOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const { error: verifyError } = await supabase.auth.verifyOtp({
        email,
        token: otpCode,
        type: "email",
      });
      if (verifyError) throw verifyError;
      // Success flows into the `session` effect above, which calls doRedeem.
    } catch (err: any) {
      setError(err.message || t('invite.failedToVerify'));
      setSubmitting(false);
    }
  };

  if (step === "loading") {
    return (
      <div className="flex min-h-dvh items-center justify-center bg-background text-muted-foreground">
        {t('invite.loading')}
      </div>
    );
  }

  if (step === "invalid") {
    return (
      <div className="flex min-h-dvh items-center justify-center px-4">
        <div className="max-w-md text-center space-y-2">
          <h1 className="text-xl font-semibold">{t('invite.invalidTitle')}</h1>
          <p className="text-muted-foreground text-sm">
            {t('invite.invalidDesc')}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-dvh flex flex-col bg-background">
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
            {/* B5 (docs/verbal-section-flow-plan.md): follow-ups can extend
                the clock, so the estimate above is a floor -- say so before
                the first "+2:00" lands mid-interview. */}
            {context?.duration_minutes && (
              <p className="text-xs text-muted-foreground mt-2">{t('invite.followupBonusNote')}</p>
            )}
          </div>

          <Card className="shadow-xl shadow-black/5 border-muted/60">
            <CardContent className="p-6 space-y-4">
              {error && (
                <div className="bg-destructive/10 border border-destructive/20 text-destructive p-3 rounded-md text-sm">
                  {error}
                </div>
              )}

              {step === "email" && (
                <form onSubmit={handleSendOtp} className="space-y-4">
                  <div className="space-y-2">
                    <label htmlFor="invite-email" className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70">
                      {t('invite.emailLabel')}
                    </label>
                    <input
                      id="invite-email"
                      required
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      className="flex h-11 w-full rounded-md border border-input bg-background px-3 py-2 text-base ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 sm:text-sm lg:h-10"
                    />
                  </div>
                  <Button
                    type="submit"
                    className="h-11 w-full lg:h-10"
                    disabled={submitting}
                  >
                    {submitting ? t('invite.sending') : t('invite.sendCode')}
                  </Button>
                </form>
              )}

              {step === "cv" && sessionId ? (
                <CvUploadStep
                  sessionId={sessionId}
                  onContinue={() => navigate(`/interviews/${sessionId}`)}
                />
              ) : step === "redeeming" ? (
                <div className="flex flex-col items-center justify-center py-8 space-y-4 animate-in fade-in zoom-in-95 duration-500">
                  <div className="h-8 w-8 rounded-full border-4 border-primary/20 border-t-primary animate-spin" />
                  <p className="text-sm font-medium text-muted-foreground">{t('invite.starting')}</p>
                </div>
              ) : step === "otp" && (
                <form onSubmit={handleVerifyOtp} className="space-y-4 animate-in fade-in duration-300">
                  <p className="text-sm text-muted-foreground">
                    <Trans i18nKey="invite.otpDesc" values={{ email }}>
                      Enter the code sent to <span className="font-medium text-foreground">{email}</span>,
                      or click the sign-in link in that same email — either one continues automatically.
                    </Trans>
                  </p>
                  <div className="space-y-2">
                    <label htmlFor="invite-otp" className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70">
                      {t('invite.otpLabel')}
                    </label>
                    <input
                      id="invite-otp"
                      required
                      type="text"
                      inputMode="numeric"
                      value={otpCode}
                      onChange={(e) => setOtpCode(e.target.value)}
                      className="flex h-11 w-full rounded-md border border-input bg-background px-3 py-2 text-base ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 sm:text-sm lg:h-10"
                      placeholder={t('invite.otpPlaceholder')}
                    />
                  </div>
                  <Button
                    type="submit"
                    className="h-11 w-full lg:h-10"
                    disabled={submitting}
                  >
                    {submitting ? t('invite.verifying') : t('invite.verifyAndContinue')}
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
