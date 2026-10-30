'use client';

import React, { useRef, useEffect } from 'react';
import { Volume2, VolumeX, Download, Mic, Music2 } from 'lucide-react';
import { StemInfo } from '@/types';
import { resolveApiUrl } from '@/lib/api';

interface StemTrackProps {
  stem: StemInfo;
  volume: number;
  isMuted: boolean;
  isSoloed: boolean;
  peaks?: number[];
  currentTime: number;
  duration: number;
  onVolumeChange: (vol: number) => void;
  onToggleMute: () => void;
  onToggleSolo: () => void;
  onSeek: (time: number) => void;
}

const STEM_CONFIGS: Record<
  string,
  { label: string; icon: any; color: string; waveColor: string; playedColor: string }
> = {
  vocals: {
    label: 'Spoken Voiceover (Pure Speech — Song & Lyrics Removed)',
    icon: Mic,
    color: 'from-emerald-500 to-green-600',
    waveColor: '#064e3b',
    playedColor: '#10b981',
  },
  voiceover: {
    label: 'Spoken Voiceover (Pure Speech — Song & Lyrics Removed)',
    icon: Mic,
    color: 'from-emerald-500 to-green-600',
    waveColor: '#064e3b',
    playedColor: '#10b981',
  },
  background_music: {
    label: 'Background Music (Clean Instrumental)',
    icon: Music2,
    color: 'from-cyan-500 to-teal-600',
    waveColor: '#164e63',
    playedColor: '#06b6d4',
  },
  instrumental: {
    label: 'Background Music (Clean Instrumental)',
    icon: Music2,
    color: 'from-cyan-500 to-teal-600',
    waveColor: '#164e63',
    playedColor: '#06b6d4',
  },
  background_song: {
    label: 'Backing Track (Music + Background Song Lyrics)',
    icon: Music2,
    color: 'from-purple-500 to-indigo-600',
    waveColor: '#3b0764',
    playedColor: '#a855f7',
  },
  other: {
    label: 'Background Song Lyrics & Singing Voice',
    icon: Music2,
    color: 'from-amber-500 to-orange-600',
    waveColor: '#78350f',
    playedColor: '#f59e0b',
  },
};

export default function StemTrack({
  stem,
  volume,
  isMuted,
  isSoloed,
  peaks = [],
  currentTime,
  duration,
  onVolumeChange,
  onToggleMute,
  onToggleSolo,
  onSeek,
}: StemTrackProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const cfg = STEM_CONFIGS[stem.stem_type] || STEM_CONFIGS.vocals;
  const Icon = cfg.icon;

  // Render responsive waveform onto HTML5 Canvas
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const width = canvas.width;
    const height = canvas.height;
    ctx.clearRect(0, 0, width, height);

    // Fallback peaks if not available
    const data = peaks.length > 0 ? peaks : Array.from({ length: 120 }, (_, i) => 0.2 + 0.6 * Math.sin(i * 0.15) ** 2);
    const numBars = data.length;
    const barWidth = width / numBars;
    const progressRatio = duration > 0 ? Math.min(1, currentTime / duration) : 0;
    const progressX = progressRatio * width;

    for (let i = 0; i < numBars; i++) {
      const x = i * barWidth;
      const barH = Math.max(3, data[i] * (height - 6));
      const y = (height - barH) / 2;

      // Color based on whether playhead has passed this bar
      ctx.fillStyle = x <= progressX ? cfg.playedColor : cfg.waveColor;
      ctx.fillRect(x, y, Math.max(1, barWidth - 1), barH);
    }

    // Playhead vertical line
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(progressX, 0, 2, height);
  }, [peaks, currentTime, duration, cfg]);

  const handleCanvasClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas || duration <= 0) return;
    const rect = canvas.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const ratio = Math.max(0, Math.min(1, clickX / rect.width));
    onSeek(ratio * duration);
  };

  return (
    <div
      className={`p-3 sm:p-4 rounded-xl border transition flex flex-col gap-3 ${
        isSoloed
          ? 'bg-amber-950/20 border-amber-500/40 shadow-sm shadow-amber-500/10'
          : isMuted
          ? 'bg-[#0f121a]/60 border-[#1a2232] opacity-60'
          : 'bg-[#121622] border-[#1f2738] hover:border-[#2b364e]'
      }`}
    >
      {/* Top Row: Track Name & Icon + Download Button */}
      <div className="flex items-center justify-between gap-3 w-full">
        <div className="flex items-center gap-3 min-w-0">
          <div
            className={`w-9 h-9 rounded-lg bg-gradient-to-tr ${cfg.color} flex items-center justify-center text-white shadow-md flex-shrink-0`}
          >
            <Icon className="w-4 h-4" />
          </div>
          <div className="min-w-0">
            <h4 className="font-semibold text-white text-sm sm:text-base tracking-tight truncate">
              {cfg.label}
            </h4>
          </div>
        </div>

        {/* Individual Download Button - Universal MP3 */}
        <a
          href={`${resolveApiUrl(stem.download_url)}&format=mp3`}
          download
          title={`Download ${cfg.label} (MP3)`}
          className="flex items-center gap-1.5 px-3.5 py-1.5 sm:px-4 sm:py-2 rounded-lg bg-violet-600 hover:bg-violet-500 text-white text-xs font-semibold shadow-md shadow-violet-600/20 transition active:scale-95 flex-shrink-0"
        >
          <Download className="w-3.5 h-3.5" />
          <span>Download (MP3)</span>
        </a>
      </div>

      {/* Middle Row: Controls (Solo, Mute, Volume Fader) + Waveform */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 w-full">
        {/* Controls container */}
        <div className="flex items-center gap-3 flex-shrink-0">
          {/* Solo & Mute Buttons */}
          <div className="flex items-center gap-1.5">
            <button
              onClick={onToggleSolo}
              title="Solo track (Listen only to this track)"
              className={`w-8 h-8 rounded-lg text-xs font-bold transition border ${
                isSoloed
                  ? 'bg-amber-500 text-black border-amber-400 shadow-md shadow-amber-500/30'
                  : 'bg-[#181e2c] text-gray-300 border-[#263045] hover:bg-[#20283a]'
              }`}
            >
              S
            </button>
            <button
              onClick={onToggleMute}
              title="Mute track"
              className={`w-8 h-8 rounded-lg text-xs font-bold transition border ${
                isMuted
                  ? 'bg-rose-500 text-white border-rose-400 shadow-md shadow-rose-500/30'
                  : 'bg-[#181e2c] text-gray-300 border-[#263045] hover:bg-[#20283a]'
              }`}
            >
              M
            </button>
          </div>

          {/* Volume Slider: up to 200% */}
          <div className="flex items-center gap-2 w-32 sm:w-36 flex-shrink-0">
            {volume === 0 || isMuted ? (
              <VolumeX className="w-4 h-4 text-gray-500 flex-shrink-0" />
            ) : (
              <Volume2 className="w-4 h-4 text-violet-400 flex-shrink-0" />
            )}
            <input
              type="range"
              min="0"
              max="2.0"
              step="0.01"
              value={volume}
              onChange={(e) => onVolumeChange(parseFloat(e.target.value))}
              onDoubleClick={() => onVolumeChange(1.0)}
              className="fader w-full"
              title={`Volume: ${Math.round(volume * 100)}%`}
            />
            <span className="text-[11px] text-gray-400 w-8 text-right">
              {Math.round(volume * 100)}%
            </span>
          </div>
        </div>

        {/* Waveform Canvas */}
        <div className="w-full flex-grow relative h-10 sm:h-12 bg-[#0b0d13] rounded-lg overflow-hidden border border-[#1a2232] cursor-pointer">
          <canvas
            ref={canvasRef}
            width={600}
            height={48}
            onClick={handleCanvasClick}
            className="w-full h-full block"
          />
        </div>
      </div>
    </div>
  );
}
