import { createContext, useContext, useState, type ReactNode } from "react";
import type { StateUpdatePayload, TranscriptionPayload, TtsStatusPayload } from "../types/realtime";

interface InterviewContextState {
  state: StateUpdatePayload | null;
  updateState: (newState: StateUpdatePayload) => void;
  // We can track local UI transient state here as well if needed
  isAgentSpeaking: boolean;
  setIsAgentSpeaking: (val: boolean) => void;
  transcriptMessages: TranscriptionPayload[];
  updateTranscript: (payload: TranscriptionPayload) => void;
  ttsStatus: TtsStatusPayload | null;
  updateTtsStatus: (payload: TtsStatusPayload) => void;
}

const InterviewContext = createContext<InterviewContextState | undefined>(undefined);

export function InterviewProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<StateUpdatePayload | null>(null);
  const [isAgentSpeaking, setIsAgentSpeaking] = useState(false);
  const [transcriptMessages, setTranscriptMessages] = useState<TranscriptionPayload[]>([]);
  const [ttsStatus, setTtsStatus] = useState<TtsStatusPayload | null>(null);

  const updateState = (newState: StateUpdatePayload) => {
    setState(newState);
  };

  const updateTranscript = (payload: TranscriptionPayload) => {
    setTranscriptMessages((prev) => {
      const idx = prev.findIndex((msg) => msg.id === payload.id);
      if (idx !== -1) {
        const updated = [...prev];
        updated[idx] = payload;
        return updated;
      }
      return [...prev, payload];
    });
  };

  const updateTtsStatus = (payload: TtsStatusPayload) => {
    setTtsStatus(payload);
  };

  return (
    <InterviewContext.Provider value={{ state, updateState, isAgentSpeaking, setIsAgentSpeaking, transcriptMessages, updateTranscript, ttsStatus, updateTtsStatus }}>
      {children}
    </InterviewContext.Provider>
  );
}

export function useInterviewStore() {
  const context = useContext(InterviewContext);
  if (!context) {
    throw new Error("useInterviewStore must be used within an InterviewProvider");
  }
  return context;
}
