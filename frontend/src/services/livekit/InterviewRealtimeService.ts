import { Room, DataPacket_Kind, RemoteParticipant } from "livekit-client";
import type { StateUpdatePayload, AllowedControl, ProctoringEventCommand, TranscriptionPayload, TtsStatusPayload } from "../../types/realtime";

type StateUpdateCallback = (state: StateUpdatePayload) => void;
type TranscriptionCallback = (transcript: TranscriptionPayload) => void;
type TtsStatusCallback = (status: TtsStatusPayload) => void;

export class InterviewRealtimeService {
  private room: Room;
  private onStateUpdate: StateUpdateCallback;
  private onTranscription?: TranscriptionCallback;
  private onTtsStatus?: TtsStatusCallback;
  private readonly boundDataHandler: (...args: any[]) => void;

  constructor(room: Room, onStateUpdate: StateUpdateCallback, onTranscription?: TranscriptionCallback, onTtsStatus?: TtsStatusCallback) {
    this.room = room;
    this.onStateUpdate = onStateUpdate;
    this.onTranscription = onTranscription;
    this.onTtsStatus = onTtsStatus;

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
      } else if (_topic === "tts_status") {
        this.onTtsStatus?.(message as TtsStatusPayload);
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

  /** PR-B: browser-detected integrity telemetry (fullscreen-exit-past-
   *  grace, tab-hidden, window-blurred). Same wire shape/transport as
   *  sendControlIntent (controller.py's process_ui_command dispatches on
   *  the same "command" string either way), but a distinct method so
   *  these always-on, never-gated events don't get typed against
   *  AllowedControl, which specifically means "server-permitted UI
   *  buttons" — a different thing than automatic browser telemetry. */
  public sendIntegrityEvent(command: ProctoringEventCommand, payload?: Record<string, unknown>) {
    const msg = {
      command,
      ...(payload && { payload }),
    };

    const encoder = new TextEncoder();
    const data = encoder.encode(JSON.stringify(msg));

    this.room.localParticipant.publishData(data, {
      reliable: true,
      topic: "ui_command",
    });
  }

  public cleanup() {
    this.room.off("dataReceived", this.boundDataHandler);
  }
}
