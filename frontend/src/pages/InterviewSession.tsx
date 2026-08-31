import { useCallback, useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { LiveKitRoom, RoomAudioRenderer } from '@livekit/components-react'
import { useTranslation } from 'react-i18next'
import { InterviewProvider } from '../stores/InterviewContext'
import { InterviewWorkspace } from '../features/interview-session/InterviewWorkspace'
import { IntroScreen } from '../features/interview-session/IntroScreen'
import { SessionEndedScreen } from '../features/interview-session/SessionEndedScreen'
import { getInterviewSession, getLiveKitToken, terminateInterview } from '../services/api/interviews'
import type { InterviewSessionResponse } from '../types/api'
import '@livekit/components-styles'

export default function InterviewSession() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { t } = useTranslation()

  const [session, setSession] = useState<InterviewSessionResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [livekitToken, setLivekitToken] = useState('')
  const [livekitUrl, setLivekitUrl] = useState('')
  const [connecting, setConnecting] = useState(false)
  // Intro screen only for a genuinely fresh session — a candidate resuming
  // mid-interview (IN_PROGRESS/DISCONNECTED after a refresh or reconnect)
  // skips straight back into the live workspace, unchanged from before.
  const [showIntro, setShowIntro] = useState(false)
  const [isEnding, setIsEnding] = useState(false)
  const [ended, setEnded] = useState(false)
  // Separate from `error` above: a failed Start/End action from the intro
  // screen should let the candidate retry right there (their instructions
  // and context are still visible), not bounce to the full-page Connection
  // Error screen the way the initial-load failure does.
  const [introError, setIntroError] = useState('')
  // Set only by init()'s initial-load branch below, for a session that was
  // ALREADY COMPLETED before this page ever connected to LiveKit. Kept
  // separate from session.status itself because markCompleted() (passed to
  // InterviewWorkspace as onCompleted) also flips session.status to
  // COMPLETED once a LIVE session finishes — that path must keep rendering
  // InterviewWorkspace (which shows the same closing screen internally,
  // still mounted inside LiveKitRoom) unchanged, not get redirected here.
  const [loadedAlreadyCompleted, setLoadedAlreadyCompleted] = useState(false)
  const markCompleted = useCallback(() => {
    setSession((current) => current && current.status !== "COMPLETED" ? { ...current, status: "COMPLETED" } : current)
  }, [])

  useEffect(() => {
    async function init() {
      if (!id) return;
      try {
        setLoading(true);
        // Fetch session status
        const sess = await getInterviewSession(id);

        setSession(sess);

        // Audit fix (2026-08-27): a session that's already COMPLETED on
        // initial load (candidate reloads/reconnects after the interview
        // finished) used to navigate to `/interviews/${id}/result` — a
        // route that was never registered in App.tsx, so it fell through
        // the catch-all into /admin, which then bounced a guest (no
        // Supabase `user`) to /login. Render Plan 11's real closing screen
        // directly instead (same component the live-completion path
        // renders via InterviewWorkspace's `isCompleted` branch — see
        // SessionEndedScreen's own docstring), and stop here: deliberately
        // skip getLiveKitToken/LiveKitRoom entirely for this case, rather
        // than falling through to the normal "resume" branch below and
        // reconnecting to a finished room. That reconnect would still work
        // for the phase-COMPLETED short-circuit inside InterviewWorkspace's
        // `isCompleted` (which already includes `session.status ===
        // "COMPLETED"` as one of its OR terms, before any live state ever
        // arrives), but it would also cause a real, separate side effect:
        // voice_adapter.py's start(resume=True) branch unconditionally
        // speaks "Welcome back! We're continuing from the {phase} phase.
        // Please go ahead." with no COMPLETED-phase exclusion — nonsensical
        // for a session that's actually finished, and audible via the still-
        // mounted RoomAudioRenderer even though nothing renders it. Not
        // fixing that here (out of today's scope, and voice_adapter.py is
        // frozen) — avoiding the reconnect path entirely sidesteps it.
        if (sess.status === "COMPLETED") {
          setLoadedAlreadyCompleted(true);
          setLoading(false);
          return;
        }

        if (sess.status === "CREATED") {
          // Fresh session — show the intro screen and defer the actual
          // LiveKit connect (and therefore the agent joining/greeting)
          // until the candidate clicks Start Session.
          setShowIntro(true);
          setLoading(false);
          return;
        }

        // Resuming an already-started session — connect immediately, same
        // as before this screen existed.
        const { token, url } = await getLiveKitToken(id);
        setLivekitToken(token);
        setLivekitUrl(url);

      } catch (err: any) {
        setError(err.message || "Failed to initialize interview session");
      } finally {
        setLoading(false);
      }
    }

    init();
  }, [id, navigate]);

  const handleStart = useCallback(async () => {
    if (!id) return;
    setConnecting(true);
    setIntroError('');
    try {
      const { token, url } = await getLiveKitToken(id);
      setLivekitToken(token);
      setLivekitUrl(url);
      setShowIntro(false);
    } catch (err: any) {
      setIntroError(err.message || t('intro.startFailed'));
    } finally {
      setConnecting(false);
    }
  }, [id, t]);

  const handleEndFromIntro = useCallback(async () => {
    if (!id) return;
    setIsEnding(true);
    setIntroError('');
    try {
      await terminateInterview(id);
      setEnded(true);
    } catch (err: any) {
      setIntroError(err.message || t('intro.endFailed'));
    } finally {
      setIsEnding(false);
    }
  }, [id, t]);

  useEffect(() => {
    // Navigation guard to prevent accidental tab closures/refreshes
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      // Only protect if we have an active session that hasn't completed
      if (session && ["CREATED", "IN_PROGRESS", "DISCONNECTED"].includes(session.status)) {
        e.preventDefault();
        // Chrome requires returnValue to be set
        e.returnValue = "";
        return "";
      }
    };

    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [session]);

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-background text-foreground">
        <div className="flex flex-col items-center gap-4">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
          <p className="text-muted-foreground">Preparing Interview Room...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-screen flex-col items-center justify-center bg-background text-foreground p-4 text-center">
        <h2 className="text-2xl font-bold mb-2 text-destructive">Connection Error</h2>
        <p className="text-muted-foreground mb-6 max-w-md">{error}</p>
        <button 
          onClick={() => window.location.reload()}
          className="rounded-md bg-primary px-4 py-2 text-primary-foreground hover:bg-primary/90"
        >
          Try Again
        </button>
      </div>
    );
  }

  if (ended) {
    return (
      <div className="flex h-screen flex-col items-center justify-center bg-background text-foreground p-4 text-center">
        <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-muted text-muted-foreground">
          <div className="h-2.5 w-2.5 rounded-full bg-current" />
        </div>
        <h2 className="text-xl font-semibold mb-2">{t('intro.endedTitle')}</h2>
        <p className="text-muted-foreground max-w-md">{t('intro.endedDesc')}</p>
      </div>
    );
  }

  if (showIntro && session) {
    return (
      <IntroScreen
        role={session.role || t('workspace.session')}
        candidateInstructions={session.candidate_instructions}
        onStart={handleStart}
        onEnd={handleEndFromIntro}
        isStarting={connecting}
        isEnding={isEnding}
        error={introError}
      />
    );
  }

  if (loadedAlreadyCompleted && session) {
    return <SessionEndedScreen session={session} />;
  }

  if (!session || !livekitToken || !livekitUrl) {
    return null;
  }

  return (
    <LiveKitRoom
      video={false}
      // Audit fix (2026-08-27): was `audio={true}` — the mic started LIVE
      // the instant the room connected, before the candidate had any
      // chance to react. If the agent was slow to join/greet, STT was
      // already processing whatever ambient sound was present in that
      // window, and a misheard/hallucinated "answer" could get treated as
      // real candidate speech before the interview had genuinely begun.
      // Starting muted (candidate explicitly unmutes via the existing mic
      // button once they're ready) closes that window entirely.
      audio={false}
      token={livekitToken}
      serverUrl={livekitUrl}
      connect={true}
      className="h-full w-full"
    >
      <RoomAudioRenderer />
      <InterviewProvider>
        <InterviewWorkspace
          session={session}
          onCompleted={markCompleted}
        />
      </InterviewProvider>
    </LiveKitRoom>
  );
}
