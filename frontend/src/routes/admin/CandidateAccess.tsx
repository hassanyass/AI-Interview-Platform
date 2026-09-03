import { useState, useEffect } from "react";
import { adminClient, type Invitation, type JobDetail } from "../../api/adminClient";
import { Users, Globe, Link as LinkIcon, Check, Copy, Send, Loader2, AlertCircle, Play } from "lucide-react";
import { Card, CardContent } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { Badge } from "../../components/ui/Badge";
import { useTranslation } from "react-i18next";
import InvitationComposer from "./InvitationComposer";

interface CandidateAccessProps {
  jobId: string;
  definition: NonNullable<JobDetail['definition']>;
  onRefresh: () => Promise<void>;
}

export default function CandidateAccess({ definition, onRefresh }: CandidateAccessProps) {
  const { t } = useTranslation();
  const [isPublic, setIsPublic] = useState(definition.is_public);
  const [accessError, setAccessError] = useState("");
  const [copied, setCopied] = useState(false);

  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [isLoadingInvites, setIsLoadingInvites] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [isInviting, setIsInviting] = useState(false);
  const [inviteError, setInviteError] = useState("");
  const [isTestingDrive, setIsTestingDrive] = useState(false);

  const publicUrl = definition.public_access_token 
    ? `${window.location.origin}/apply/${definition.public_access_token}`
    : "";

  const fetchInvitations = async () => {
    setIsLoadingInvites(true);
    try {
      const data = await adminClient.listInvitations(definition.id);
      setInvitations(data);
    } catch (err: any) {
      console.error(err);
    } finally {
      setIsLoadingInvites(false);
    }
  };

  useEffect(() => {
    fetchInvitations();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [definition.id]);

  const handleToggleAccess = async (newIsPublic: boolean) => {
    if (newIsPublic === isPublic) return;
    setAccessError("");
    try {
      await adminClient.updateDefinition(definition.id, { is_public: newIsPublic });
      await onRefresh();
      setIsPublic(newIsPublic);
    } catch (err: any) {
      setAccessError(err.message || t('candidateAccess.failedToUpdateAccess'));
    }
  };

  const handleCopyLink = () => {
    if (!publicUrl) return;
    navigator.clipboard.writeText(publicUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleInvite = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inviteEmail.trim()) return;
    setIsInviting(true);
    setInviteError("");
    try {
      await adminClient.createInvitation(definition.id, inviteEmail.trim());
      setInviteEmail("");
      await fetchInvitations();
    } catch (err: any) {
      setInviteError(err.message || t('candidateAccess.failedToInvite'));
    } finally {
      setIsInviting(false);
    }
  };

  const handleTestDrive = async () => {
    setIsTestingDrive(true);
    setAccessError("");
    try {
      const response = await adminClient.createTestDrive(definition.id);
      // We got the session token, open the interview in a new tab
      // For the frontend to pick it up, it usually takes it from the URL or localStorage
      // But typically, the apply flow sets it in localStorage and redirects.
      // We can do that manually here:
      const authData = {
        token: response.access_token,
        session_id: response.session.id,
        livekit_token: response.livekit_token,
        livekit_url: response.livekit_url,
      };
      localStorage.setItem(`interview_auth_${response.session.id}`, JSON.stringify(authData));
      window.open(`/interview/${response.session.id}`, "_blank");
    } catch (err: any) {
      setAccessError(err.message || "Failed to start test drive");
    } finally {
      setIsTestingDrive(false);
    }
  };

  return (
    <div className="space-y-6 mt-10">
      <div className="flex items-center justify-between gap-4 mb-4 pb-2 border-b border-border/50">
        <div>
          <h2 className="text-xl font-bold tracking-tight text-foreground">{t('candidateAccess.title')}</h2>
          <p className="text-sm text-muted-foreground">{t('candidateAccess.manageAccessDescription')}</p>
        </div>
        <Button 
          onClick={handleTestDrive} 
          disabled={isTestingDrive} 
          variant="outline" 
          className="gap-2 shrink-0 border-primary/20 hover:bg-primary/5 text-primary rounded-xl font-semibold"
        >
          {isTestingDrive ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4 fill-current" />}
          {t('candidateAccess.testInterview')}
        </Button>
      </div>

      {accessError && (
        <div className="bg-red-50 text-red-600 p-4 rounded-xl text-sm font-medium flex items-center gap-2 border border-red-100">
          <AlertCircle className="h-4 w-4" />
          {accessError}
        </div>
      )}

      {/* Access Settings Card */}
      <Card className="overflow-hidden border-border/60 shadow-sm rounded-2xl">
        <CardContent className="p-6 md:p-8">
          <div className="flex flex-col md:flex-row gap-8">
            
            {/* Options */}
            <div className="flex-1 space-y-4">
              <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Access Mode</label>
              
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {/* Invitation Only Mode */}
                <div 
                  onClick={() => handleToggleAccess(false)}
                  className={`
                    cursor-pointer rounded-xl p-5 border-2 transition-all duration-200 relative
                    ${!isPublic 
                      ? "border-primary bg-primary/[0.03] shadow-sm" 
                      : "border-transparent bg-muted/40 hover:bg-muted/80 hover:border-border"}
                  `}
                >
                  <div className="flex items-center gap-3 mb-3">
                    <div className={`
                      flex h-10 w-10 shrink-0 items-center justify-center rounded-full transition-colors
                      ${!isPublic ? "bg-primary text-white shadow-md" : "bg-white text-muted-foreground shadow-sm"}
                    `}>
                      <Users className="h-5 w-5" />
                    </div>
                    <div className={`font-bold text-base leading-tight ${!isPublic ? "text-primary" : "text-foreground"}`}>
                      {t('candidateAccess.invitationOnly')}
                    </div>
                  </div>
                  <p className={`text-sm leading-relaxed ${!isPublic ? "text-foreground/90" : "text-muted-foreground"}`}>
                    {t('candidateAccess.invitationOnlyDesc')}
                  </p>
                  
                  {/* Selection Indicator */}
                  {!isPublic && (
                    <div className="absolute top-4 right-4 h-5 w-5 rounded-full bg-primary flex items-center justify-center text-white shadow-sm">
                      <Check className="h-3 w-3 stroke-[3]" />
                    </div>
                  )}
                </div>

                {/* Public Access Mode */}
                <div 
                  onClick={() => handleToggleAccess(true)}
                  className={`
                    cursor-pointer rounded-xl p-5 border-2 transition-all duration-200 relative
                    ${isPublic 
                      ? "border-primary bg-primary/[0.03] shadow-sm" 
                      : "border-transparent bg-muted/40 hover:bg-muted/80 hover:border-border"}
                  `}
                >
                  <div className="flex items-center gap-3 mb-3">
                    <div className={`
                      flex h-10 w-10 shrink-0 items-center justify-center rounded-full transition-colors
                      ${isPublic ? "bg-primary text-white shadow-md" : "bg-white text-muted-foreground shadow-sm"}
                    `}>
                      <Globe className="h-5 w-5" />
                    </div>
                    <div className={`font-bold text-base leading-tight ${isPublic ? "text-primary" : "text-foreground"}`}>
                      {t('candidateAccess.publicAccess')}
                    </div>
                  </div>
                  <p className={`text-sm leading-relaxed ${isPublic ? "text-foreground/90" : "text-muted-foreground"}`}>
                    {t('candidateAccess.publicAccessDesc')}
                  </p>
                  
                  {/* Selection Indicator */}
                  {isPublic && (
                    <div className="absolute top-4 right-4 h-5 w-5 rounded-full bg-primary flex items-center justify-center text-white shadow-sm">
                      <Check className="h-3 w-3 stroke-[3]" />
                    </div>
                  )}
                </div>
              </div>
            </div>

          </div>

          {/* Public Link Callout */}
          {isPublic && definition.public_access_token && (
            <div className="mt-8 pt-6 border-t border-border/60 animate-in fade-in slide-in-from-top-2 duration-300">
              <label className="text-sm font-bold text-foreground mb-3 flex items-center gap-2">
                <LinkIcon className="h-4 w-4 text-primary" />
                {t('candidateAccess.publicLink')}
              </label>
              <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
                <div className="bg-muted/30 border border-border/60 rounded-xl px-4 py-3 text-sm flex-1 truncate font-mono text-foreground/80 shadow-inner">
                  {publicUrl}
                </div>
                <div className="flex gap-2">
                  <Button 
                    variant="outline" 
                    onClick={handleCopyLink} 
                    className="flex-1 sm:flex-none gap-2 rounded-xl h-11 border-border hover:bg-muted/50"
                  >
                    {copied ? <Check className="h-4 w-4 text-green-600" /> : <Copy className="h-4 w-4 text-muted-foreground" />}
                    <span className={copied ? "text-green-600 font-medium" : "font-medium"}>
                      {copied ? t('candidateAccess.copied') : t('candidateAccess.copyLink')}
                    </span>
                  </Button>
                  <a href={publicUrl} target="_blank" rel="noopener noreferrer" className="flex-none">
                    <Button variant="secondary" className="w-11 h-11 p-0 rounded-xl bg-secondary text-secondary-foreground hover:bg-secondary/90 shadow-sm" title="Open in new tab">
                      <Globe className="h-4 w-4" />
                    </Button>
                  </a>
                </div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Invitations Section */}
      <div className="grid lg:grid-cols-3 gap-6 items-start">
        
        {/* Invite Form */}
        <Card className="lg:col-span-1 shadow-sm rounded-2xl border-border/60">
          <CardContent className="p-6 space-y-5">
            <h3 className="font-bold text-lg flex items-center gap-2 text-foreground">
              <Send className="h-5 w-5 text-primary" />
              <span>{t('candidateAccess.inviteCandidate')}</span>
            </h3>
            
            {inviteError && (
              <div className="text-sm bg-red-50 text-red-600 p-3 rounded-xl flex items-start gap-2 border border-red-100">
                <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
                <span>{inviteError}</span>
              </div>
            )}
            
            <form onSubmit={handleInvite} className="flex flex-col gap-4">
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">{t('candidateAccess.emailAddress')}</label>
                <input
                  type="email"
                  required
                  placeholder="candidate@example.com"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  className="w-full bg-white border border-input rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all placeholder:text-muted-foreground/50 shadow-sm"
                />
              </div>
              <Button 
                type="submit" 
                disabled={isInviting || !inviteEmail.trim()} 
                className="w-full h-11 rounded-xl bg-primary text-white font-semibold hover:bg-primary/90 shadow-md transition-all active:scale-[0.98]"
              >
                {isInviting ? <Loader2 className="h-5 w-5 animate-spin" /> : t('candidateAccess.invite')}
              </Button>
            </form>
          </CardContent>
        </Card>

        {/* Invitations List */}
        <Card className="lg:col-span-2 shadow-sm rounded-2xl border-border/60 overflow-hidden">
          <div className="px-6 py-4 border-b border-border/50 bg-muted/20 flex items-center justify-between">
            <h3 className="font-bold text-foreground">
              {t('candidateAccess.invitationsSent')}
            </h3>
            <Badge variant="secondary" className="rounded-full px-3 py-1 bg-white border-border shadow-sm text-xs">
              {invitations.length} Total
            </Badge>
          </div>
          
          <CardContent className="p-0">
            {isLoadingInvites ? (
              <div className="p-12 flex justify-center">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground/40" />
              </div>
            ) : invitations.length === 0 ? (
              <div className="p-12 text-center flex flex-col items-center">
                <div className="h-12 w-12 rounded-full bg-muted/50 flex items-center justify-center mb-3">
                  <Users className="h-6 w-6 text-muted-foreground/50" />
                </div>
                <p className="text-sm font-medium text-foreground/70">
                  {t('candidateAccess.noInvitations')}
                </p>
                <p className="text-xs text-muted-foreground mt-1">
                  Invite a candidate to get started.
                </p>
              </div>
            ) : (
              <div className="max-h-[350px] overflow-y-auto">
                <table className="w-full text-sm text-left">
                  <thead className="bg-white sticky top-0 border-b border-border/50 shadow-sm z-10">
                    <tr>
                      <th className="font-semibold text-muted-foreground px-6 py-3">{t('candidateAccess.email')}</th>
                      <th className="font-semibold text-muted-foreground px-6 py-3">{t('candidateAccess.status')}</th>
                      <th className="font-semibold text-muted-foreground px-6 py-3 text-right">{t('candidateAccess.date')}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/40">
                    {invitations.map((inv) => (
                      <tr key={inv.id} className="hover:bg-muted/10 transition-colors">
                        <td className="px-6 py-4 truncate max-w-[200px] font-medium" title={inv.candidate_email}>
                          {inv.candidate_email}
                        </td>
                        <td className="px-6 py-4">
                          <Badge variant={
                            inv.status === "STARTED" ? "success" : 
                            inv.status === "INVITED" ? "default" : "secondary"
                          } className="text-xs rounded-full px-2.5 py-0.5 capitalize shadow-sm">
                            {inv.status.toLowerCase()}
                          </Badge>
                        </td>
                        <td className="px-6 py-4 text-muted-foreground text-right tabular-nums text-xs">
                          {new Date(inv.created_at).toLocaleDateString(undefined, { 
                            year: 'numeric', 
                            month: 'short', 
                            day: 'numeric' 
                          })}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* New (2026-09-03): compose one message, send to several candidates
          at once, with an AI-regeneratable draft. Deliberately a separate
          surface from the quick single-email form above -- that one is
          real (creates an actual InterviewInvitation row the OTP flow
          depends on); this one's Send is a stub for now, see
          InvitationComposer.tsx's own docstring. */}
      <InvitationComposer definitionId={definition.id} />
    </div>
  );
}
