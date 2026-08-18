import { Room, DataPacket_Kind, RemoteParticipant } from "livekit-client";
import type { StateUpdatePayload, AllowedControl, TranscriptionPayload } from "../../types/realtime";

type StateUpdateCallback = (state: StateUpdatePayload) => void;
type TranscriptionCallback = (transcript: TranscriptionPayload) => void;

export class InterviewRealtimeService {
  private room: Room;
  private onStateUpdate: StateUpdateCallback;
  private onTranscription?: TranscriptionCallback;
  private readonly boundDataHandler: (...args: any[]) => void;

  constructor(room: Room, onStateUpdate: StateUpdateCallback, onTranscription?: TranscriptionCallback) {
    this.room = room;
    this.onStateUpdate = onStateUpdate;
    this.onTranscription = onTranscription;
    
    // Subscribe to incoming data messages
    this.boundDataHandler = this.handleDataReceived.bind(this);
    this.room.on("dataReceived", this.boundDataHandler);
  }

  private handleDataReceived(
    payload: Uint8Array,
    _participant?: RemoteParticipant,
    _kind?: DataPacket_Kind,
    _topic?: string
  ) {
    try {
      const decoder = new TextDecoder();
      const strData = decoder.decode(payload);
      const message = JSON.parse(strData);

      if (_topic === "state_update") {
        this.onStateUpdate(message as StateUpdatePayload);
      } else if (_topic === "transcription") {
        this.onTranscription?.(message as TranscriptionPayload);
      }
    } catch (e) {
      console.warn("Failed to parse data channel message:", e);
    }
  }

  public sendControlIntent(intent: AllowedControl, payload?: any) {
    const msg = {
      command: intent,
      ...(payload && { payload }),
    };

    const encoder = new TextEncoder();
    const data = encoder.encode(JSON.stringify(msg));

    // Send to all participants (the agent will intercept)
    this.room.localParticipant.publishData(data, {
      reliable: true,
      topic: "ui_command"
    });
  }

  public cleanup() {
    this.room.off("dataReceived", this.boundDataHandler);
  }
}
