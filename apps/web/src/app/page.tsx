'use client';

import React, { useState } from 'react';
import Navbar from '@/components/Navbar';
import AudioUploader from '@/components/AudioUploader';
import SeparationStatus from '@/components/SeparationStatus';
import StemMixer from '@/components/StemMixer';
import { SeparationJob, Project } from '@/types';
import { getProject } from '@/lib/api';
import { Sparkles, Mic, Music2 } from 'lucide-react';

export default function StudioPage() {
  const [viewState, setViewState] = useState<'upload' | 'processing' | 'mixer'>('upload');
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [activeProjectId, setActiveProjectId] = useState<string | null>(null);
  const [activeJob, setActiveJob] = useState<SeparationJob | null>(null);
  const [activeProject, setActiveProject] = useState<Project | null>(null);

  const handleSeparationStarted = (jobId: string, projectId: string) => {
    setActiveJobId(jobId);
    setActiveProjectId(projectId);
    setViewState('processing');
  };

  const handleSeparationComplete = async (job: SeparationJob) => {
    setActiveJob(job);
    try {
      const proj = await getProject(job.project_id);
      setActiveProject(proj);
      setViewState('mixer');
    } catch (e) {
      console.error('Failed to load project after separation:', e);
    }
  };

  const handleSeparationFailed = (errMsg: string) => {
    console.error('Separation failed:', errMsg);
  };

  const handleNewSeparation = () => {
    setViewState('upload');
    setActiveJobId(null);
    setActiveProjectId(null);
    setActiveJob(null);
    setActiveProject(null);
  };

  return (
    <div className="min-h-screen bg-[#0b0d13] text-gray-100 flex flex-col selection:bg-violet-500/30">
      <Navbar />

      <main className="flex-1 max-w-5xl mx-auto w-full px-4 sm:px-6 py-6 sm:py-10 space-y-8 sm:space-y-10">
        {/* Simple Friendly Hero */}
        {viewState === 'upload' && (
          <div className="text-center space-y-3 max-w-2xl mx-auto pt-2 sm:pt-4">
            <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-violet-500/10 border border-violet-500/20 text-xs font-medium text-violet-300">
              <Sparkles className="w-3.5 h-3.5 text-violet-400" />
              <span>Simple Voice & Music Isolator</span>
            </div>
            <h1 className="text-2xl sm:text-4xl font-extrabold tracking-tight bg-gradient-to-b from-white via-gray-100 to-gray-400 bg-clip-text text-transparent">
              Separate Speech & Background Music
            </h1>
            <p className="text-xs sm:text-sm text-gray-400 max-w-lg mx-auto leading-relaxed">
              Upload any audio or video file to extract clear foreground speech and background music into two clean tracks.
            </p>
          </div>
        )}

        {/* View Switcher: Upload -> Processing -> Mixer */}
        <div className="transition-all duration-300">
          {viewState === 'upload' && (
            <AudioUploader onSeparationStarted={handleSeparationStarted} />
          )}

          {viewState === 'processing' && activeJobId && activeProjectId && (
            <SeparationStatus
              jobId={activeJobId}
              projectId={activeProjectId}
              onComplete={handleSeparationComplete}
              onFailed={handleSeparationFailed}
            />
          )}

          {viewState === 'mixer' && activeJob && activeProject && (
            <StemMixer
              job={activeJob}
              project={activeProject}
              onNewSeparation={handleNewSeparation}
            />
          )}
        </div>

        {/* Simple 2-Card Feature Highlights */}
        {viewState === 'upload' && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 max-w-2xl mx-auto pt-6 border-t border-[#1f2738]/60">
            <div className="p-4 sm:p-5 rounded-2xl bg-[#121622] border border-[#1f2738] flex items-start gap-3.5">
              <div className="w-9 h-9 rounded-xl bg-emerald-600/20 border border-emerald-500/30 flex items-center justify-center text-emerald-400 flex-shrink-0">
                <Mic className="w-4 h-4" />
              </div>
              <div>
                <h3 className="font-semibold text-white text-sm">Foreground Speech</h3>
                <p className="text-xs text-gray-400 mt-1 leading-relaxed">
                  Clear spoken voice with background music, songs, and background noise removed.
                </p>
              </div>
            </div>

            <div className="p-4 sm:p-5 rounded-2xl bg-[#121622] border border-[#1f2738] flex items-start gap-3.5">
              <div className="w-9 h-9 rounded-xl bg-cyan-600/20 border border-cyan-500/30 flex items-center justify-center text-cyan-400 flex-shrink-0">
                <Music2 className="w-4 h-4" />
              </div>
              <div>
                <h3 className="font-semibold text-white text-sm">Background Music</h3>
                <p className="text-xs text-gray-400 mt-1 leading-relaxed">
                  Clean soundtrack and musical accompaniment without any talking or speech.
                </p>
              </div>
            </div>
          </div>
        )}
      </main>

      {/* Simple Footer */}
      <footer className="w-full border-t border-[#1f2738] bg-[#0b0d13] py-5 text-center text-xs text-gray-500">
        <div className="max-w-5xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-2">
          <span>SoundSplit • Speech & Music Isolator</span>
          <span className="text-gray-400">Audio and video files are processed on demand</span>
        </div>
      </footer>
    </div>
  );
}
