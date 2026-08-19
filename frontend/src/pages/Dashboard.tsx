import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, BriefcaseBusiness, CheckCircle2, Clock3, Plus, Sparkles, XCircle, Loader2 } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { API_BASE_URL } from "../lib/api";
import { AppShell } from "../components/layout/AppShell";

interface SessionSummary { id: string; role: string; level: string; language: string; status: string; created_at: string; started_at?: string; completed_at?: string; configuration?: { duration: number; thinking_time: number } }

const levelLabel: Record<string, string> = { junior: "Junior", mid: "Mid-level", senior: "Senior" };
const statusLabel: Record<string, string> = { CREATED: "Ready to start", IN_PROGRESS: "In progress", COMPLETED: "Completed", TERMINATED: "Ended", ENDED: "Ended", CANCELLED: "Cancelled", CANCELED: "Cancelled", DISCONNECTED: "Disconnected", FAILED: "Needs attention" };

function normalizedStatus(status: string | undefined) {
  return status?.trim().toUpperCase() || "UNKNOWN";
}

function formatDate(value: string) { return new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }); }

export default function Dashboard() {
  const { user, getAccessToken } = useAuth();
  const [profile, setProfile] = useState<any>(null);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [terminating, setTerminating] = useState(false);
  const [activeError, setActiveError] = useState("");
  const [endedSessionIds, setEndedSessionIds] = useState<Set<string>>(() => new Set());

  const fetchSessions = useCallback(async () => {
    const token = await getAccessToken();
    if (!token) return;
    const response = await fetch(`${API_BASE_URL}/api/v1/interviews/`, { headers: { Authorization: `Bearer ${token}` } });
    if (!response.ok) throw new Error("Could not load interview sessions.");
    setSessions(await response.json());
  }, [getAccessToken]);

  useEffect(() => {
    async function fetchData() {
      const token = await getAccessToken();
      if (!token) return;
      try {
        const [profileRes, sessionsRes] = await Promise.all([
          fetch(`${API_BASE_URL}/api/v1/profiles/me`, { headers: { Authorization: `Bearer ${token}` } }),
          fetch(`${API_BASE_URL}/api/v1/interviews/`, { headers: { Authorization: `Bearer ${token}` } }),
        ]);
        if (profileRes.ok) setProfile(await profileRes.json());
        if (sessionsRes.ok) setSessions(await sessionsRes.json());
      } catch (error) { console.error("Failed to load dashboard", error); } finally { setLoading(false); }
    }
    fetchData();
  }, [getAccessToken]);

  // CREATED is only a newly-created setup record, not an interview in progress.
  // Only IN_PROGRESS can be resumed. A completion timestamp is terminal even if
  // an older record still carries a stale status.
  const isResumableSession = (item: SessionSummary) => {
    const status = normalizedStatus(item.status);
    return status === "IN_PROGRESS" && !item.completed_at && !endedSessionIds.has(item.id);
  };
  const activeSessions = sessions.filter(isResumableSession);
  const activeSession = activeSessions[0];
  const completedSessions = sessions.filter((item) => normalizedStatus(item.status) === "COMPLETED");
  const firstName = profile?.full_name?.split(" ")[0] || user?.user_metadata?.full_name?.split(" ")[0] || user?.user_metadata?.name?.split(" ")[0] || "there";
  const profileReady = Boolean(profile?.professional_title || profile?.skills?.length || profile?.resumes?.length);
  const stats = useMemo(() => ({ total: sessions.length, completed: completedSessions.length, active: activeSession ? 1 : 0 }), [sessions.length, completedSessions.length, activeSession]);

  const terminateActiveSession = async () => {
    if (!activeSession || terminating) return;
    if (!window.confirm("End this interview and remove it from your active workspace?")) return;
    setTerminating(true); setActiveError("");
    try {
      const token = await getAccessToken();
      const responses = await Promise.all(activeSessions.map((session) => fetch(`${API_BASE_URL}/api/v1/interviews/${session.id}/terminate`, { method: "POST", headers: { Authorization: `Bearer ${token}` } })));
      if (responses.some((response) => !response.ok)) throw new Error("Could not end all active interviews.");
      // Remove it immediately, then reconcile with the backend so stale resumable
      // records cannot return after a refresh or another dashboard request.
      setEndedSessionIds((current) => new Set([...current, ...activeSessions.map((session) => session.id)]));
      setSessions((current) => current.filter((item) => !activeSessions.some((session) => session.id === item.id)));
      await fetchSessions();
    } catch (error: any) { setActiveError(error.message || "Could not end the active interview."); }
    finally { setTerminating(false); }
  };

  if (loading) return <AppShell><div className="flex min-h-[60vh] items-center justify-center text-sm text-slate-500">Preparing your workspace...</div></AppShell>;

  return <AppShell>
    <div className="space-y-8">
      <section className="flex flex-col justify-between gap-5 lg:flex-row lg:items-end">
        <div><p className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Candidate workspace</p><h1 className="text-3xl font-semibold tracking-[-0.03em] text-slate-950 sm:text-4xl">Good morning, {firstName}.</h1><p className="mt-3 max-w-xl text-sm leading-6 text-slate-500">Your interview practice, profile context, and assessment history in one place.</p></div>
        <Link to="/interviews/new" className="inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-slate-950 px-4 text-sm font-semibold text-white shadow-sm transition hover:bg-slate-800"><Plus className="h-4 w-4" /> New interview</Link>
      </section>

      <section className="grid gap-3 sm:grid-cols-3">
        {[{ label: "All interviews", value: stats.total, icon: BriefcaseBusiness }, { label: "Completed", value: stats.completed, icon: CheckCircle2 }, { label: "Active now", value: stats.active, icon: Clock3 }].map(({ label, value, icon: Icon }) => <div key={label} className="flex items-center gap-4 rounded-xl border border-slate-200 bg-white px-5 py-4 shadow-[0_1px_2px_rgba(15,23,42,0.03)]"><span className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-100 text-slate-600"><Icon className="h-4 w-4" /></span><div><p className="text-2xl font-semibold tracking-tight text-slate-950">{value}</p><p className="text-xs font-medium text-slate-500">{label}</p></div></div>)}
      </section>

      {!profileReady && <section className="flex flex-col gap-4 rounded-xl border border-sky-200 bg-sky-50/70 p-5 sm:flex-row sm:items-center sm:justify-between"><div className="flex gap-3"><Sparkles className="mt-0.5 h-5 w-5 shrink-0 text-sky-700" /><div><p className="text-sm font-semibold text-sky-950">Make your interview more relevant</p><p className="mt-1 text-sm leading-6 text-sky-800/80">Add your resume so questions can reflect your experience and target role.</p></div></div><Link to="/profile" className="inline-flex shrink-0 items-center gap-2 text-sm font-semibold text-sky-800 hover:text-sky-950">Complete profile <ArrowRight className="h-4 w-4" /></Link></section>}

      {activeSession ? <section className="overflow-hidden rounded-2xl border border-slate-200 bg-slate-950 text-white shadow-[0_12px_32px_rgba(15,23,42,0.12)]"><div className="grid gap-8 p-6 sm:p-8 lg:grid-cols-[1fr_auto] lg:items-end"><div><div className="mb-5 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-slate-400"><span className="h-2 w-2 rounded-full bg-emerald-400" /> {normalizedStatus(activeSession.status) === "IN_PROGRESS" ? "Interview in progress" : "Interview ready"}</div><h2 className="text-2xl font-semibold tracking-[-0.03em] sm:text-3xl">{activeSession.role}</h2><p className="mt-3 text-sm text-slate-400">{levelLabel[activeSession.level] || activeSession.level} <span className="mx-2 text-slate-600">/</span> {activeSession.language === "ar" ? "Arabic" : "English"} <span className="mx-2 text-slate-600">/</span> {activeSession.configuration?.duration || 15} min</p></div><div className="flex flex-col gap-2 sm:flex-row"><Link to={`/interviews/${activeSession.id}`} className="inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-white px-5 text-sm font-semibold text-slate-950 transition hover:bg-slate-100">{normalizedStatus(activeSession.status) === "IN_PROGRESS" ? "Resume interview" : "Start interview"}<ArrowRight className="h-4 w-4" /></Link><Link to="/interviews/new" className="inline-flex h-11 items-center justify-center gap-2 rounded-lg border border-white/20 px-5 text-sm font-semibold text-white transition hover:bg-white/10"><Plus className="h-4 w-4" /> New interview</Link><button type="button" onClick={terminateActiveSession} disabled={terminating} className="inline-flex h-11 items-center justify-center gap-2 rounded-lg border border-red-300/30 px-5 text-sm font-semibold text-red-200 transition hover:bg-red-400/10 disabled:opacity-60">{terminating ? <Loader2 className="h-4 w-4 animate-spin" /> : <XCircle className="h-4 w-4" />} End session</button></div></div>{activeError && <div className="border-t border-red-300/20 px-6 py-3 text-xs text-red-200 sm:px-8">{activeError}</div>}<div className="border-t border-white/10 px-6 py-3 text-xs text-slate-400 sm:px-8">One focused technical problem, guided conversation, and a structured assessment at the end.</div></section> : <section className="rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center"><span className="mx-auto flex h-11 w-11 items-center justify-center rounded-xl bg-slate-100 text-slate-500"><BriefcaseBusiness className="h-5 w-5" /></span><h2 className="mt-4 text-lg font-semibold text-slate-950">Create New Session</h2><p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-500">Set the role, language, and difficulty, then start a focused interview session.</p><Link to="/interviews/new" className="mt-5 inline-flex items-center gap-2 text-sm font-semibold text-slate-950 hover:text-sky-700">Create New Session <ArrowRight className="h-4 w-4" /></Link></section>}

      {completedSessions.length > 0 && <section className="space-y-4"><div className="flex items-center justify-between"><div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Assessment history</p><h2 className="mt-1 text-xl font-semibold tracking-tight text-slate-950">Recent interviews</h2></div><span className="text-xs text-slate-400">{completedSessions.length} total</span></div><div className="overflow-hidden rounded-xl border border-slate-200 bg-white">{completedSessions.map((session, index) => <Link key={session.id} to={`/interviews/${session.id}/result`} className={`flex items-center justify-between gap-4 px-5 py-4 transition hover:bg-slate-50 sm:px-6 ${index !== completedSessions.length - 1 ? "border-b border-slate-100" : ""}`}><div className="flex min-w-0 items-center gap-3"><span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-500"><BriefcaseBusiness className="h-4 w-4" /></span><div className="min-w-0"><p className="truncate text-sm font-semibold text-slate-900">{session.role}</p><p className="mt-1 text-xs text-slate-500">{levelLabel[session.level] || session.level} · {formatDate(session.created_at)}</p></div></div><span className="flex shrink-0 items-center gap-2 text-xs font-medium text-slate-500"><span className={`h-2 w-2 rounded-full ${normalizedStatus(session.status) === "COMPLETED" ? "bg-emerald-500" : "bg-slate-300"}`} />{statusLabel[normalizedStatus(session.status)] || normalizedStatus(session.status)}<ArrowRight className="ml-2 h-3.5 w-3.5 text-slate-300" /></span></Link>)}</div></section>}
    </div>
  </AppShell>;
}
