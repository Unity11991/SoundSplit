'use client';

import React, { useEffect, useState } from 'react';
import { CheckCircle2, AlertTriangle, Sparkles } from 'lucide-react';
import { subscribeSeparationEvents, getSeparation } from '@/lib/api';
import { SeparationJob } from '@/types';

interface SeparationStatusProps {
  jobId: string;
  projectId: string;
  onComplete: (job: SeparationJob) => void;
  onFailed: (errorMsg: string) => void;
}

export default function SeparationStatus({
  jobId,
  projectId,
  onComplete,
  onFailed,
}: SeparationStatusProps) {
  const [progress, setProgress] = useState(10);
  const [stage, setStage] = useState('Separating Speech & Background Music...');
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [status, setStatus] = useState<'queued' | 'processing' | 'completed' | 'failed'>('processing');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Timer for elapsed seconds
  useEffect(() => {
    const timer = setInterval(() => {
      setElapsedSeconds((prev) => prev + 1);
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  // SSE subscription & fallback polling
  useEffect(() => {
    let isFinished = false;

    const handleEvent = (event: any) => {
      if (event.progress !== undefined) {
        setProgress(event.progress);
      }
      if (event.stage) {
        // Map any technical stage strings to simple friendly text
        let friendly = event.stage;
        if (friendly.toLowerCase().includes('model') || friendly.toLowerCase().includes('neural') || friendly.toLowerCase().includes('network')) {
          friendly = 'Separating Speech & Background Music...';
        } else if (friendly.toLowerCase().includes('decode') || friendly.toLowerCase().includes('preprocess')) {
          friendly = 'Reading and preparing audio...';
        } else if (friendly.toLowerCase().includes('enhance') || friendly.toLowerCase().includes('noise')) {
          friendly = 'Enhancing speech & cleaning background noise...';
        } else if (friendly.toLowerCase().includes('rendering') || friendly.toLowerCase().includes('reconstruct') || friendly.toLowerCase().includes('metadata')) {
          friendly = 'Finalizing your audio files...';
        }
        setStage(friendly);
      }
      if (event.status === 'completed') {
        isFinished = true;
        setStatus('completed');
        getSeparation(jobId)
          .then((job) => onComplete(job))
          .catch((err) => console.error(err));
      } else if (event.status === 'failed') {
        isFinished = true;
        setStatus('failed');
        const err = event.error_message || 'Could not process audio.';
        setErrorMessage(err);
        onFailed(err);
      }
    };

    const unsubscribe = subscribeSeparationEvents(
      jobId,
      handleEvent,
      (err) => console.warn('Connecting to progress stream...', err)
    );

    // Polling fallback every 2.5 seconds
    const pollInterval = setInterval(async () => {
      if (isFinished) return;
      try {
        const job = await getSeparation(jobId);
        setProgress(job.progress);
        if (job.status === 'completed') {
          isFinished = true;
          setStatus('completed');
          onComplete(job);
        } else if (job.status === 'failed') {
          isFinished = true;
          setStatus('failed');
          setErrorMessage(job.error_message || 'Failed to separate audio.');
          onFailed(job.error_message || 'Failed to separate audio.');
        }
      } catch (e) {
        console.error('Check progress:', e);
      }
    }, 2500);

    return () => {
      unsubscribe();
      clearInterval(pollInterval);
    };
  }, [jobId, onComplete, onFailed]);

  const formatTime = (secs: number) => {
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return `${m}:${s < 10 ? '0' : ''}${s}`;
  };

  return (
    <div className="w-full max-w-xl mx-auto p-6 sm:p-8 rounded-2xl bg-[#121622] border border-[#1f2738] shadow-2xl relative overflow-hidden space-y-6">
      {/* Background glow */}
      <div className="absolute -top-32 -right-32 w-64 h-64 bg-violet-600/15 rounded-full blur-3xl animate-pulse pointer-events-none" />

      {/* Header */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-violet-600/20 border border-violet-500/30 flex items-center justify-center text-violet-400 flex-shrink-0">
            {status === 'failed' ? (
              <AlertTriangle className="w-5 h-5 text-rose-400" />
            ) : status === 'completed' ? (
              <CheckCircle2 className="w-5 h-5 text-emerald-400" />
            ) : (
              <Sparkles className="w-5 h-5 text-violet-400 animate-spin" />
            )}
          </div>
          <div>
            <h3 className="font-semibold text-white tracking-tight text-base sm:text-lg">
              {status === 'completed'
                ? 'Separation Complete!'
                : status === 'failed'
                ? 'Processing Error'
                : 'Separating Speech & Music'}
            </h3>
            <p className="text-xs text-gray-400">Please wait while your tracks are created</p>
          </div>
        </div>

        <div className="px-3 py-1 rounded-full bg-[#181e2c] border border-[#263045] text-xs font-mono text-gray-300">
          {formatTime(elapsedSeconds)}
        </div>
      </div>

      {/* Soundwave animation */}
      {status === 'processing' && (
        <div className="flex items-center justify-center gap-1.5 h-14 bg-[#0b0d13]/60 rounded-xl px-4 border border-[#1a2232]">
          {[...Array(20)].map((_, i) => (
            <div
              key={i}
              className="w-1.5 bg-gradient-to-t from-violet-600 to-cyan-400 rounded-full"
              style={{
                height: `${Math.max(15, ((Math.sin(i * 0.5 + elapsedSeconds * 2.5) + 1) / 2) * 85)}%`,
                transition: 'height 0.2s ease',
              }}
            />
          ))}
        </div>
      )}

      {/* Progress Bar & Stage */}
      <div className="space-y-2.5">
        <div className="flex justify-between items-center text-xs sm:text-sm">
          <span className="text-gray-300 font-medium truncate pr-2">
            {stage}
          </span>
          <span className="font-mono font-bold text-violet-400 flex-shrink-0">{progress}%</span>
        </div>

        <div className="w-full h-2.5 rounded-full bg-[#1a2232] overflow-hidden p-[1px] border border-[#263045]">
          <div
            className="h-full rounded-full bg-gradient-to-r from-violet-600 to-cyan-400 transition-all duration-300 shadow-md shadow-violet-500/30"
            style={{ width: `${Math.max(4, progress)}%` }}
          />
        </div>
      </div>

      {/* Stage milestones */}
      <div className="grid grid-cols-3 gap-2 text-[11px] text-gray-400 text-center pt-1">
        <div className={`p-2 rounded-lg ${progress >= 20 ? 'bg-violet-950/40 text-violet-300 font-medium' : 'bg-[#0f121a]'}`}>
          1. Loading
        </div>
        <div className={`p-2 rounded-lg ${progress >= 40 ? 'bg-violet-950/40 text-violet-300 font-medium' : 'bg-[#0f121a]'}`}>
          2. Separating
        </div>
        <div className={`p-2 rounded-lg ${progress >= 95 ? 'bg-violet-950/40 text-violet-300 font-medium' : 'bg-[#0f121a]'}`}>
          3. Ready
        </div>
      </div>

      {/* Error state */}
      {status === 'failed' && (
        <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-sm">
          <p className="font-semibold">Failed to process:</p>
          <p className="text-xs text-rose-400 mt-1">{errorMessage}</p>
        </div>
      )}
    </div>
  );
}
