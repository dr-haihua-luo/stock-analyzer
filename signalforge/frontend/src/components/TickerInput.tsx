import { useCallback, useEffect, useRef, useState } from 'react';
import {
  isRecordingSupported, startRecording, MAX_RECORD_MS, type Recording,
} from '../lib/recordWav';

type VoiceState = 'idle' | 'listening' | 'transcribing';
type Hint = { kind: 'ok' | 'warn' | 'error'; text: string } | null;

interface Props {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  disabled?: boolean;
}

export default function TickerInput({ value, onChange, onSubmit, disabled }: Props) {
  const [state, setState] = useState<VoiceState>('idle');
  const [hint, setHint] = useState<Hint>(null);
  const recRef = useRef<Recording | null>(null);
  const timerRef = useRef<number | null>(null);
  const supported = isRecordingSupported();

  const clearTimer = () => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  };

  // release the mic if the component unmounts mid-recording
  useEffect(() => () => { clearTimer(); recRef.current?.cancel(); }, []);

  // success hints fade out; warnings/errors stay until the next attempt
  useEffect(() => {
    if (hint?.kind !== 'ok') return;
    const t = window.setTimeout(() => setHint(null), 8000);
    return () => window.clearTimeout(t);
  }, [hint]);

  const finish = useCallback(async () => {
    clearTimer();
    const rec = recRef.current;
    recRef.current = null;
    if (!rec) return;
    setState('transcribing');
    try {
      const wav = await rec.stop();
      const response = await fetch('/api/speech/transcribe', {
        method: 'POST',
        body: wav,
        headers: { 'Content-Type': 'audio/wav' },
      });
      if (!response.ok) {
        if (response.status === 503) {
          throw new Error('Voice input is not available on the server (Whistle not installed).');
        }
        throw new Error('Voice input failed. You can still type the ticker.');
      }
      const data: { transcript: string; ticker: string | null; latency_ms: number } = await response.json();
      if (data.ticker) {
        onChange(data.ticker);
        setHint({ kind: 'ok', text: `Heard "${data.transcript}" -> ${data.ticker}` });
      } else if (data.transcript) {
        setHint({
          kind: 'warn',
          text: `Heard "${data.transcript}" but couldn't match a ticker. Try again or type it.`,
        });
      } else {
        setHint({ kind: 'warn', text: "Didn't catch anything. Try again." });
      }
    } catch (err: any) {
      setHint({
        kind: 'error',
        text: err?.message || 'Voice input failed. You can still type the ticker.',
      });
    } finally {
      setState('idle');
    }
  }, [onChange]);

  const toggle = async () => {
    if (disabled || state === 'transcribing') return;
    if (state === 'listening') { await finish(); return; }
    setHint(null);
    try {
      recRef.current = await startRecording();
      setState('listening');
      timerRef.current = window.setTimeout(() => { void finish(); }, MAX_RECORD_MS);
    } catch (err: any) {
      setHint({
        kind: 'error',
        text:
          err?.name === 'NotAllowedError' ? 'Microphone permission denied. Allow it in your browser settings.'
          : err?.name === 'NotFoundError' ? 'No microphone found.'
          : 'Could not start the microphone.',
      });
    }
  };

  const listening = state === 'listening';
  const busy = state === 'transcribing';

  return (
    <div className="flex-1">
      <div className="relative">
        <input
          value={value}
          onChange={(e) => onChange(e.target.value.toUpperCase())}
          onKeyDown={(e) => { if (e.key === 'Enter') onSubmit(); }}
          placeholder={supported ? 'Type a ticker or tap the mic' : 'Ticker (e.g., AAPL, MSFT, GOOGL)'}
          maxLength={10}
          aria-label="Stock ticker"
          className="w-full pr-11 px-4 py-2 border border-gray-300 rounded-lg
                     bg-white text-gray-900 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        {supported && (
          <button
            type="button"
            onClick={toggle}
            disabled={disabled || busy}
            aria-label={listening ? 'Stop listening' : 'Speak a ticker'}
            aria-pressed={listening}
            title={listening ? 'Click to stop' : 'Speak a ticker'}
            className={`absolute right-1.5 top-1/2 -translate-y-1/2 w-8 h-8 rounded-md
                        flex items-center justify-center transition-colors
                        ${listening ? 'bg-red-600 text-white animate-pulse'
                                    : 'text-gray-500 hover:text-gray-800 hover:bg-gray-200'}
                        disabled:opacity-50`}
          >
            {busy ? (
              <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="3" opacity="0.25" />
                <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
              </svg>
            ) : (
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                   strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="9" y="2" width="6" height="12" rx="3" />
                <path d="M5 11a7 7 0 0 0 14 0" />
                <path d="M12 18v4" />
              </svg>
            )}
          </button>
        )}
      </div>

      {(listening || busy || hint) && (
        <p role="status" className={`mt-1 text-xs ${
          listening ? 'text-red-600'
          : busy ? 'text-gray-500'
          : hint?.kind === 'ok' ? 'text-green-600'
          : hint?.kind === 'warn' ? 'text-amber-600'
          : 'text-red-600'}`}>
          {listening ? 'Listening… say the ticker or company name, click the mic when done'
           : busy ? 'Transcribing…'
           : hint?.text}
        </p>
      )}
    </div>
  );
}
