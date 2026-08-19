import { useCallback, useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { LiveKitRoom, RoomAudioRenderer } from '@livekit/components-react'
import { InterviewProvider } from '../stores/InterviewContext'
import { InterviewWorkspace } from '../features/interview-session/InterviewWorkspace'
import { getInterviewSession, getLiveKitToken } from '../services/api/interviews'
import type { InterviewSessionResponse } from '../types/api'
import '@livekit/components-styles'

export default function InterviewSession() {
  const { id } = useParams()
  const navigate = useNavigate()
  
  const [session, setSession] = useState<InterviewSessionResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  
  const [livekitToken, setLivekitToken] = useState('')
  const [livekitUrl, setLivekitUrl] = useState('')
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
        
        // If it's already COMPLETED, go to results
        if (sess.status === "COMPLETED") {
          navigate(`/interviews/${id}/result`);
          return;
        }

        setSession(sess);

        // Fetch LiveKit connection details
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

  if (!session || !livekitToken || !livekitUrl) {
    return null;
  }

  return (
    <LiveKitRoom
      video={false}
      audio={true}
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
