import { useState } from "react";
import { adminClient } from "../../api/adminClient";
import { Sparkles, X, Loader2, Send, Construction } from "lucide-react";
import { Card, CardContent } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";

/**
 * Invitation email composer (2026-09-03) -- a genuinely separate surface
 * from CandidateAccess.tsx's existing "Invite Candidate" quick-form
 * above it. That existing form is real: one email in, a real
 * InterviewInvitation row out, the actual OTP flow depends on it.
 *
 * This composer is deliberately NOT wired to that -- per the explicit
 * scope for this pass ("emails not yet and not needed for this demo"),
 * Send is a stub. The one piece of real functionality here is
 * "Regenerate": a genuine AI-drafted subject/body via the backend's own
 * independent Groq call (invitation_message_generator.py), which HR can
 * then freely edit. Multiple recipients are collected as removable chips
 * purely for this composer's own UI state -- nothing is persisted until
 * a real send path exists (CURRENT_DECISIONS.md's P1, still deferred).
 */

const DEFAULT_SUBJECT = "You're invited to interview";
const DEFAULT_BODY =
  "Hi there,\n\n" +
  "We'd like to invite you to the next step in our hiring process — a short, voice-based AI interview you can complete online at a time that works for you.\n\n" +
  "Click \"Regenerate\" above to draft a version tailored to this specific role, or edit this message directly.\n\n" +
  "We look forward to hearing from you.";

function isLikelyEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());
}

export default function InvitationComposer({ definitionId }: { definitionId: string }) {
  const [recipients, setRecipients] = useState<string[]>([]);
  const [emailDraft, setEmailDraft] = useState("");
  const [emailError, setEmailError] = useState("");

  const [subject, setSubject] = useState(DEFAULT_SUBJECT);
  const [body, setBody] = useState(DEFAULT_BODY);
  const [isGenerating, setIsGenerating] = useState(false);
  const [generateError, setGenerateError] = useState("");

  const [sendAttempted, setSendAttempted] = useState(false);

  const addRecipient = (raw: string) => {
    const candidate = raw.trim().replace(/,$/, "");
    if (!candidate) return;
    if (!isLikelyEmail(candidate)) {
      setEmailError(`"${candidate}" doesn't look like a valid email address.`);
      return;
    }
    setEmailError("");
    setRecipients((prev) => (prev.includes(candidate) ? prev : [...prev, candidate]));
    setEmailDraft("");
  };

  const handleEmailKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" || e.key === "," || e.key === "Tab") {
      if (emailDraft.trim()) {
        e.preventDefault();
        addRecipient(emailDraft);
      }
    } else if (e.key === "Backspace" && !emailDraft && recipients.length > 0) {
      setRecipients((prev) => prev.slice(0, -1));
    }
  };

  const removeRecipient = (email: string) => {
    setRecipients((prev) => prev.filter((r) => r !== email));
  };

  const handleRegenerate = async () => {
    setIsGenerating(true);
    setGenerateError("");
    try {
      const draft = await adminClient.generateInvitationMessage(definitionId);
      setSubject(draft.subject);
      setBody(draft.body);
    } catch (err: any) {
      setGenerateError(err.message || "Failed to generate a draft message");
    } finally {
      setIsGenerating(false);
    }
  };

  const handleSend = () => {
    // Deliberate stub -- see this file's module docstring. No request is
    // made; nothing is persisted or sent.
    setSendAttempted(true);
  };

  return (
    <Card className="shadow-sm rounded-2xl border-border/60">
      <CardContent className="p-6 md:p-8 space-y-6">
        <div>
          <h3 className="font-bold text-lg text-foreground">Compose Invitation Email</h3>
          <p className="text-sm text-muted-foreground mt-0.5">
            Draft one message and send it to multiple candidates at once.
          </p>
        </div>

        {/* Recipients -- chip input */}
        <div className="space-y-1.5">
          <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            Recipients
          </label>
          <div
            className="flex flex-wrap items-center gap-2 w-full bg-white border border-input rounded-xl px-3 py-2.5 min-h-[46px] focus-within:ring-2 focus-within:ring-primary/20 focus-within:border-primary transition-all"
            onClick={(e) => {
              if (e.currentTarget === e.target) {
                (e.currentTarget.querySelector("input") as HTMLInputElement | null)?.focus();
              }
            }}
          >
            {recipients.map((email) => (
              <span
                key={email}
                className="inline-flex items-center gap-1.5 rounded-full bg-secondary/10 text-secondary text-sm font-medium pl-3 pr-1.5 py-1"
              >
                {email}
                <button
                  type="button"
                  onClick={() => removeRecipient(email)}
                  aria-label={`Remove ${email}`}
                  className="rounded-full p-0.5 hover:bg-secondary/20 transition-colors"
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            ))}
            <input
              type="text"
              value={emailDraft}
              onChange={(e) => setEmailDraft(e.target.value)}
              onKeyDown={handleEmailKeyDown}
              onBlur={() => emailDraft.trim() && addRecipient(emailDraft)}
              placeholder={recipients.length === 0 ? "candidate@example.com, then Enter" : "Add another…"}
              className="flex-1 min-w-[160px] bg-transparent text-sm outline-none placeholder:text-muted-foreground/50"
            />
          </div>
          {emailError && <p className="text-xs text-destructive">{emailError}</p>}
        </div>

        {/* Message -- placeholder template, editable, AI-regeneratable */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              Message
            </label>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={handleRegenerate}
              disabled={isGenerating}
              className="gap-1.5"
            >
              {isGenerating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5 text-primary" />}
              {isGenerating ? "Generating…" : "Regenerate"}
            </Button>
          </div>
          {generateError && <p className="text-xs text-destructive">{generateError}</p>}

          <input
            type="text"
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            className="w-full bg-white border border-input rounded-xl px-4 py-2.5 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all"
            placeholder="Subject"
          />
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={7}
            className="w-full bg-white border border-input rounded-xl px-4 py-3 text-sm leading-relaxed focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all resize-y"
            placeholder="Message body"
          />
          <p className="text-xs text-muted-foreground">
            This is a starting draft — edit it however you like before sending.
          </p>
        </div>

        {sendAttempted && (
          <div className="flex items-start gap-2.5 rounded-xl border border-warning/30 bg-warning/10 px-4 py-3 text-sm text-foreground">
            <Construction className="h-4 w-4 shrink-0 text-warning mt-0.5" />
            <p>Sending isn't available yet — this feature is under development. Your draft and recipient list weren't lost; you can keep editing.</p>
          </div>
        )}

        <div className="flex justify-end">
          <Button
            type="button"
            onClick={handleSend}
            disabled={recipients.length === 0}
            className="gap-2 rounded-xl h-11 px-6"
          >
            <Send className="h-4 w-4" />
            Send to {recipients.length || ""} Candidate{recipients.length === 1 ? "" : "s"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
