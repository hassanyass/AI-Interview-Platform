import { useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { supabase } from "../lib/supabase";
import { useAuth } from "../context/AuthContext";
import {
  getInvitationContext,
  redeemInvitation,
  type InvitationPublicContext,
} from "../services/api/publicInvitations";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { LanguageToggle } from "../components/ui/LanguageToggle";
import { useTranslation, Trans } from 'react-i18next';

type Step = "loading" | "invalid" | "email" | "otp" | "redeeming";

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
      navigate(`/interviews/${redeemResult.session.id}`);
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
      <div className="flex min-h-screen items-center justify-center bg-background text-muted-foreground">
        {t('invite.loading')}
      </div>
    );
  }

  if (step === "invalid") {
    return (
      <div className="flex h-screen items-center justify-center px-4">
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

              {step === "email" && (
                <form onSubmit={handleSendOtp} className="space-y-4">
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
                  <Button
                    type="submit"
                    className="w-full"
                    disabled={submitting}
                  >
                    {submitting ? t('invite.sending') : t('invite.sendCode')}
                  </Button>
                </form>
              )}

              {(step === "otp" || step === "redeeming") && (
                <form onSubmit={handleVerifyOtp} className="space-y-4">
                  <p className="text-sm text-muted-foreground">
                    <Trans i18nKey="invite.otpDesc" values={{ email }}>
                      Enter the code sent to <span className="font-medium text-foreground">{email}</span>,
                      or click the sign-in link in that same email — either one continues automatically.
                    </Trans>
                  </p>
                  <div className="space-y-2">
                    <label className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70">
                      {t('invite.otpLabel')}
                    </label>
                    <input
                      required
                      type="text"
                      inputMode="numeric"
                      value={otpCode}
                      onChange={(e) => setOtpCode(e.target.value)}
                      className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                      placeholder={t('invite.otpPlaceholder')}
                    />
                  </div>
                  <Button
                    type="submit"
                    className="w-full"
                    disabled={submitting || step === "redeeming"}
                  >
                    {step === "redeeming" ? t('invite.starting') : submitting ? t('invite.verifying') : t('invite.verifyAndContinue')}
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
