'use client';

import React, { useEffect, useState, useRef } from 'react';
import { Play, Pause, Square, Volume2, RotateCcw, Sparkles } from 'lucide-react';
import { SeparationJob, Project } from '@/types';
import { StemLabAudioEngine, PlaybackMode } from '@/lib/audioEngine';
import { getProjectPeaks, deleteProject, resolveApiUrl } from '@/lib/api';
import StemTrack from './StemTrack';

interface StemMixerProps {
  job: SeparationJob;
  project: Project;
  onNewSeparation: () => void;
}

export default function StemMixer({ job, project, onNewSeparation }: StemMixerProps) {
  const engineRef = useRef<StemLabAudioEngine | null>(null);

  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(project.duration_seconds || 0);
  const [mode, setMode] = useState<PlaybackMode>('stems');
  const [masterVolume, setMasterVolume] = useState(1.0);
  const [peaks, setPeaks] = useState<Record<string, number[]>>({});

  // Stems to display: Pure Speech, Clean Instrumental Music, and Backing Track (with Song Lyrics)
  const visibleStems = job.stems.filter(
    (s) =>
      s.stem_type === 'vocals' ||
      s.stem_type === 'background_music' ||
      s.stem_type === 'instrumental' ||
      s.stem_type === 'background_song'
  );

  // Track volume, solo, mute states
  const [trackStates, setTrackStates] = useState<
    Record<string, { volume: number; isMuted: boolean; isSoloed: boolean }>
  >({});

  // Initialize Audio Engine and load stems + original natively
  useEffect(() => {
    let isCancelled = false;
    const engine = new StemLabAudioEngine();
    engineRef.current = engine;

    // Initialize track states: Speech & Clean Music active; Backing Song muted by default to prevent audio doubling
    const initialStates: Record<string, { volume: number; isMuted: boolean; isSoloed: boolean }> = {};
    visibleStems.forEach((s) => {
      const isVoice = s.stem_type === 'vocals' || s.stem_type === 'voiceover';
      const isBackingSong = s.stem_type === 'background_song' || s.stem_type === 'other';
      initialStates[s.id] = {
        volume: isVoice ? 1.3 : 0.85,
        isMuted: isBackingSong,
        isSoloed: false,
      };
    });
    setTrackStates(initialStates);

    // Fetch precomputed waveform peaks
    getProjectPeaks(project.id).then((p) => {
      if (!isCancelled) setPeaks(p);
    });

    // Concurrently load audio in background without blocking playback
    const loadAudio = async () => {
      try {
        const promises: Promise<any>[] = [];
        if (project.original_url && !isCancelled) {
          promises.push(engine.loadOriginal(resolveApiUrl(project.original_url)));
        }
        for (const stem of visibleStems) {
          if (isCancelled) break;
          promises.push(engine.addStemTrack(stem.id, stem.stem_type, resolveApiUrl(stem.stream_url)));
        }
        await Promise.all(promises);

        if (!isCancelled && engine.getDuration() > 0) {
          setDuration(engine.getDuration());
        }
      } catch (err) {
        if (!isCancelled) {
          console.error('Audio engine loading:', err);
        }
      }
    };

    loadAudio();

    // Engine subscriptions
    const unsubTime = engine.onTimeUpdate((time, dur) => {
      if (!isCancelled) {
        setCurrentTime(time);
        if (dur > 0) setDuration(dur);
      }
    });

    const unsubState = engine.onStateChange((playing, curMode) => {
      if (!isCancelled) {
        setIsPlaying(playing);
        setMode(curMode);
      }
    });

    // Keyboard shortcut: Spacebar toggles Play/Pause
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.code === 'Space' && (e.target as HTMLElement).tagName !== 'INPUT') {
        e.preventDefault();
        if (engineRef.current) {
          if (isPlaying) {
            engineRef.current.pause();
          } else {
            engineRef.current.play();
          }
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);

    return () => {
      isCancelled = true;
      window.removeEventListener('keydown', handleKeyDown);
      unsubTime();
      unsubState();
      engine.destroy();
    };
  }, [job.id, project.id]);

  const handlePlayPause = () => {
    if (!engineRef.current) return;
    if (isPlaying) {
      engineRef.current.pause();
    } else {
      engineRef.current.play();
    }
  };

  const handleStop = () => {
    engineRef.current?.stop();
  };

  const handleSeek = (time: number) => {
    engineRef.current?.seek(time);
  };

  const handleModeToggle = (newMode: PlaybackMode) => {
    setMode(newMode);
    engineRef.current?.setMode(newMode);
  };

  const handleMasterVolumeChange = (vol: number) => {
    setMasterVolume(vol);
    engineRef.current?.setMasterVolume(vol);
  };

  const handleTrackVolumeChange = (stemId: string, vol: number) => {
    setTrackStates((prev) => ({
      ...prev,
      [stemId]: { ...prev[stemId], volume: vol },
    }));
    engineRef.current?.setTrackVolume(stemId, vol);
  };

  const handleToggleMute = (stemId: string) => {
    setTrackStates((prev) => ({
      ...prev,
      [stemId]: { ...prev[stemId], isMuted: !prev[stemId]?.isMuted },
    }));
    engineRef.current?.toggleMute(stemId);
  };

  const handleToggleSolo = (stemId: string) => {
    setTrackStates((prev) => ({
      ...prev,
      [stemId]: { ...prev[stemId], isSoloed: !prev[stemId]?.isSoloed },
    }));
    engineRef.current?.toggleSolo(stemId);
  };

  // Immediate server cleanup on new separation
  const handleNewSeparationWithCleanup = async () => {
    try {
      await deleteProject(project.id);
    } catch (err) {
      console.warn('Auto-cleanup project:', err);
    }
    onNewSeparation();
  };

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins < 10 ? '0' : ''}${mins}:${secs < 10 ? '0' : ''}${secs}`;
  };

  return (
    <div className="w-full max-w-4xl mx-auto space-y-5 px-2 sm:px-0">
      {/* Simple Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between p-4 sm:p-5 rounded-2xl bg-[#121622] border border-[#1f2738] gap-4">
        <div>
          <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-xs font-medium mb-1.5">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <span>Separation Ready</span>
          </div>
          <h2 className="text-base sm:text-lg font-bold text-white tracking-tight truncate max-w-sm sm:max-w-md">
            {project.original_filename || project.name}
          </h2>
          <p className="text-xs text-gray-400 mt-0.5">Duration: {formatTime(duration)}</p>
        </div>

        <button
          onClick={handleNewSeparationWithCleanup}
          className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-[#181e2c] hover:bg-[#20283a] text-gray-200 border border-[#263045] text-xs font-semibold transition active:scale-95 cursor-pointer w-full sm:w-auto justify-center"
        >
          <RotateCcw className="w-4 h-4" />
          <span>Upload Another File</span>
        </button>
      </div>

      {/* Master Controls Bar */}
      <div className="p-3.5 sm:p-4 rounded-2xl bg-[#0f121a] border border-[#1f2738] shadow-xl flex flex-col sm:flex-row items-center justify-between gap-3.5 sticky top-16 z-40 backdrop-blur-md bg-[#0f121a]/95">
        {/* Playback Buttons & Time */}
        <div className="flex items-center justify-between w-full sm:w-auto gap-3">
          <div className="flex items-center gap-2">
            <button
              onClick={handlePlayPause}
              className="w-11 h-11 sm:w-12 sm:h-12 rounded-xl flex items-center justify-center transition shadow-lg bg-gradient-to-tr from-violet-600 to-indigo-600 text-white hover:scale-105 active:scale-95 shadow-violet-600/30 cursor-pointer"
              title="Play / Pause"
            >
              {isPlaying ? <Pause className="w-5 h-5 fill-current" /> : <Play className="w-5 h-5 fill-current ml-0.5" />}
            </button>

            <button
              onClick={handleStop}
              className="w-9 h-9 sm:w-10 sm:h-10 rounded-xl bg-[#181e2c] hover:bg-[#222a3d] text-gray-300 border border-[#263045] flex items-center justify-center transition cursor-pointer"
              title="Stop"
            >
              <Square className="w-3.5 h-3.5 sm:w-4 sm:h-4 fill-current" />
            </button>
          </div>

          {/* Time Counter */}
          <div className="px-3 py-1.5 rounded-xl bg-[#0b0d13] border border-[#1f2738] text-xs sm:text-sm tracking-wider flex items-center gap-1.5 font-medium font-mono">
            <span className="text-violet-400 font-semibold">{formatTime(currentTime)}</span>
            <span className="text-gray-500">/</span>
            <span className="text-gray-400">{formatTime(duration)}</span>
          </div>
        </div>

        {/* Audio Mode Toggle */}
        <div className="flex items-center bg-[#0b0d13] p-1 rounded-xl border border-[#1f2738] w-full sm:w-auto justify-center">
          <button
            onClick={() => handleModeToggle('original')}
            className={`flex-1 sm:flex-none px-3.5 py-1.5 rounded-lg text-xs font-semibold transition ${
              mode === 'original'
                ? 'bg-gradient-to-r from-violet-600 to-indigo-600 text-white shadow-md'
                : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            Original Audio
          </button>
          <button
            onClick={() => handleModeToggle('stems')}
            className={`flex-1 sm:flex-none px-3.5 py-1.5 rounded-lg text-xs font-semibold transition flex items-center justify-center gap-1.5 ${
              mode === 'stems'
                ? 'bg-gradient-to-r from-cyan-600 to-teal-600 text-white shadow-md'
                : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            <Sparkles className="w-3.5 h-3.5" />
            <span>Separated Audio</span>
          </button>
        </div>

        {/* Master Volume */}
        <div className="flex items-center gap-2.5 w-full sm:w-40">
          <Volume2 className="w-4 h-4 text-gray-400 flex-shrink-0" />
          <input
            type="range"
            min="0"
            max="1.5"
            step="0.01"
            value={masterVolume}
            onChange={(e) => handleMasterVolumeChange(parseFloat(e.target.value))}
            className="fader w-full"
            title={`Volume: ${Math.round(masterVolume * 100)}%`}
          />
          <span className="text-xs text-gray-400 w-8 text-right font-mono">
            {Math.round(masterVolume * 100)}%
          </span>
        </div>
      </div>

      {/* Individual Stem Tracks: Only Vocal (Foreground Speech) and Background Music */}
      <div className="space-y-3">
        {visibleStems.map((stem) => {
          const tState = trackStates[stem.id] || { volume: 1.0, isMuted: false, isSoloed: false };
          const stemPeaks = peaks[stem.stem_type] || [];
          return (
            <StemTrack
              key={stem.id}
              stem={stem}
              volume={tState.volume}
              isMuted={tState.isMuted}
              isSoloed={tState.isSoloed}
              peaks={stemPeaks}
              currentTime={currentTime}
              duration={duration}
              onVolumeChange={(vol) => handleTrackVolumeChange(stem.id, vol)}
              onToggleMute={() => handleToggleMute(stem.id)}
              onToggleSolo={() => handleToggleSolo(stem.id)}
              onSeek={handleSeek}
            />
          );
        })}
      </div>
    </div>
  );
}
