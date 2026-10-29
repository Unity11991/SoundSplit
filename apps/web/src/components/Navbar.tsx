'use client';

import React, { useEffect, useState, useRef } from 'react';
import Link from 'next/link';
import { Sparkles, HardDrive, Trash2, CheckCircle2, RefreshCw } from 'lucide-react';
import { getReadiness, getStorageStatus, triggerStorageCleanup } from '@/lib/api';

export default function Navbar() {
  const [isReady, setIsReady] = useState(false);
  const [storageStats, setStorageStats] = useState<{ total_mb: number; max_storage_mb: number; quota_used_percent: number } | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [isCleaning, setIsCleaning] = useState(false);
  const [cleanMessage, setCleanMessage] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  const fetchStorage = async () => {
    try {
      const stats = await getStorageStatus();
      if (stats) setStorageStats(stats);
    } catch {
      // ignore in navbar background
    }
  };

  useEffect(() => {
    let isCancelled = false;

    const checkStatus = async () => {
      try {
        const res = await getReadiness();
        if (!isCancelled && res) {
          setIsReady(res.status === 'ready' || res.checks?.ai_engine?.status === 'ok');
        }
      } catch {
        if (!isCancelled) setIsReady(false);
      }
    };

    checkStatus();
    fetchStorage();

    const interval = setInterval(() => {
      checkStatus();
      fetchStorage();
    }, 10000);

    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);

    return () => {
      isCancelled = true;
      clearInterval(interval);
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, []);

  const handleCleanStorage = async () => {
    setIsCleaning(true);
    setCleanMessage(null);
    try {
      const res = await triggerStorageCleanup();
      setCleanMessage(`Freed ${res.freed_mb} MB!`);
      await fetchStorage();
      setTimeout(() => setCleanMessage(null), 3000);
    } catch {
      setCleanMessage('Cleanup failed');
      setTimeout(() => setCleanMessage(null), 3000);
    } finally {
      setIsCleaning(false);
    }
  };

  return (
    <header className="sticky top-0 z-50 w-full border-b border-[#1f2738] bg-[#0b0d13]/90 backdrop-blur-md">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
        {/* Brand */}
        <Link href="/" className="flex items-center gap-2.5 group">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-violet-600 to-cyan-500 p-[1px] shadow-md shadow-violet-500/20 group-hover:shadow-violet-500/40 transition">
            <div className="w-full h-full bg-[#0b0d13] rounded-xl flex items-center justify-center">
              <Sparkles className="w-4 h-4 text-violet-400 group-hover:scale-110 transition" />
            </div>
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="font-bold text-base sm:text-lg tracking-tight bg-gradient-to-r from-white via-gray-100 to-gray-400 bg-clip-text text-transparent">
                SoundSplit
              </span>
            </div>
            <p className="text-[10px] text-gray-400 tracking-wide">Voice & Music Isolator</p>
          </div>
        </Link>

        {/* Right Actions */}
        <div className="flex items-center gap-2 sm:gap-3">
          {/* Intelligent Storage Indicator & Quick Cleanup */}
          <div className="relative" ref={menuRef}>
            <button
              onClick={() => setIsOpen(!isOpen)}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[#121622] hover:bg-[#181d2c] border border-[#1f2738] text-[11px] text-gray-300 transition"
              title="Storage Management"
            >
              <HardDrive className="w-3.5 h-3.5 text-cyan-400" />
              <span>{storageStats ? `${storageStats.total_mb} MB` : 'Storage'}</span>
            </button>

            {isOpen && (
              <div className="absolute right-0 mt-2 w-64 p-3 rounded-xl bg-[#0f121d] border border-[#1f2738] shadow-2xl z-50 animate-in fade-in zoom-in-95">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-semibold text-white">Storage Usage</span>
                  <span className="text-[10px] text-cyan-400 font-mono">
                    {storageStats ? `${storageStats.total_mb} MB / ${storageStats.max_storage_mb} MB` : 'Calculating...'}
                  </span>
                </div>

                {/* Progress bar */}
                <div className="w-full bg-[#1a2030] h-1.5 rounded-full overflow-hidden mb-3">
                  <div
                    className="bg-gradient-to-r from-cyan-500 to-violet-500 h-full rounded-full transition-all duration-300"
                    style={{ width: `${Math.min(storageStats?.quota_used_percent || 0, 100)}%` }}
                  />
                </div>

                <p className="text-[10px] text-gray-400 mb-3 leading-relaxed">
                  Automatic intelligent cleanup purges temporary files and expired songs every 30 minutes.
                </p>

                {cleanMessage && (
                  <div className="mb-2 p-1.5 text-center text-xs text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 rounded-lg">
                    {cleanMessage}
                  </div>
                )}

                <button
                  onClick={handleCleanStorage}
                  disabled={isCleaning}
                  className="w-full py-1.5 px-3 rounded-lg bg-[#181f30] hover:bg-[#202940] border border-[#2b354e] text-xs font-medium text-white flex items-center justify-center gap-2 transition disabled:opacity-50"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${isCleaning ? 'animate-spin text-cyan-400' : 'text-gray-400'}`} />
                  <span>{isCleaning ? 'Cleaning Storage...' : 'Clean Temporary Files'}</span>
                </button>
              </div>
            )}
          </div>

          {/* Simple AI Status */}
          <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-[#121622] border border-[#1f2738] text-xs">
            <span
              className={`w-2 h-2 rounded-full ${
                isReady ? 'bg-emerald-400 animate-pulse' : 'bg-amber-400 animate-ping'
              }`}
            />
            <span className="text-gray-300 text-[11px] font-medium">
              {isReady ? 'AI Ready' : 'Connecting...'}
            </span>
          </div>
        </div>
      </div>
    </header>
  );
}
