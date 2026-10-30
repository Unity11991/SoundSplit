'use client';

import React, { useState, useRef } from 'react';
import { UploadCloud, Music, Wand2, CheckCircle2, AlertCircle, FileAudio, Sparkles, Film, Video } from 'lucide-react';
import { uploadAudio, createSeparation } from '@/lib/api';

interface AudioUploaderProps {
  onSeparationStarted: (jobId: string, projectId: string) => void;
}

const VALID_AUDIO_EXTENSIONS = ['wav', 'mp3', 'flac', 'm4a', 'aac', 'ogg', 'opus', 'wma', 'aiff', 'aif'];
const VALID_VIDEO_EXTENSIONS = ['mp4', 'mkv', 'mov', 'avi', 'webm', 'flv', 'm4v', 'wmv', 'ts'];
const ALL_VALID_EXTENSIONS = [...VALID_AUDIO_EXTENSIONS, ...VALID_VIDEO_EXTENSIONS];

export default function AudioUploader({ onSeparationStarted }: AudioUploaderProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadPercent, setUploadPercent] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFileSelected(e.dataTransfer.files[0]);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFileSelected(e.target.files[0]);
    }
  };

  const isVideoFile = (file: File): boolean => {
    const ext = file.name.split('.').pop()?.toLowerCase();
    return (ext ? VALID_VIDEO_EXTENSIONS.includes(ext) : false) || (file.type ? file.type.startsWith('video/') : false);
  };

  const handleFileSelected = (file: File) => {
    setError(null);
    const ext = file.name.split('.').pop()?.toLowerCase();
    const isExtensionValid = ext && ALL_VALID_EXTENSIONS.includes(ext);
    const isMimeValid = file.type && (file.type.startsWith('audio/') || file.type.startsWith('video/'));

    if (!isExtensionValid && !isMimeValid) {
      setError(`Format ".${ext || 'unknown'}" is not supported. Please upload an audio or video file.`);
      return;
    }

    if (file.size > 300 * 1024 * 1024) {
      setError(`File size (${(file.size / (1024 * 1024)).toFixed(1)}MB) exceeds 300MB maximum limit.`);
      return;
    }

    setSelectedFile(file);
  };

  const handleStartSeparation = async () => {
    if (!selectedFile) return;

    setIsUploading(true);
    setUploadPercent(0);
    setError(null);

    try {
      // 1. Upload file (video audio is automatically extracted)
      const uploadResult = await uploadAudio(selectedFile, (pct) => {
        setUploadPercent(pct);
      });

      // 2. Start separation: always voiceover mode (Speech & Background Music)
      const separationJob = await createSeparation(uploadResult.project_id, 'voiceover', 'htdemucs');

      onSeparationStarted(separationJob.id, uploadResult.project_id);
    } catch (err: any) {
      setError(err.message || 'An error occurred during upload or separation.');
      setIsUploading(false);
    }
  };

  const isCurrentFileVideo = selectedFile ? isVideoFile(selectedFile) : false;

  return (
    <div className="w-full max-w-3xl mx-auto space-y-5 px-2 sm:px-0">
      {/* Upload Dropzone */}
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={`relative border-2 border-dashed rounded-2xl p-6 sm:p-10 text-center transition overflow-hidden ${
          isDragging
            ? 'border-violet-500 bg-violet-950/20 shadow-xl shadow-violet-500/10'
            : selectedFile
            ? 'border-[#263045] bg-[#121622]/80'
            : 'border-[#1f2738] bg-[#0f121a]/60 hover:border-violet-500/40 hover:bg-[#121622]/60'
        }`}
      >
        {/* Full-coverage native file input: supports both audio & video */}
        {!selectedFile && (
          <input
            ref={fileInputRef}
            type="file"
            id="audio-file-input"
            accept=".wav,.mp3,.flac,.m4a,.aac,.ogg,.opus,.wma,.aiff,.aif,.mp4,.mkv,.mov,.avi,.webm,.flv,.m4v,.wmv,.ts,audio/*,video/*"
            className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-20"
            onChange={handleFileChange}
            onClick={(e) => {
              (e.target as HTMLInputElement).value = '';
            }}
            disabled={isUploading}
            title="Click or drag and drop an audio or video file"
          />
        )}

        {/* Ambient background glow */}
        <div className="absolute -top-24 -left-24 w-64 h-64 bg-violet-600/10 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute -bottom-24 -right-24 w-64 h-64 bg-cyan-600/10 rounded-full blur-3xl pointer-events-none" />

        <div className="relative z-10 flex flex-col items-center">
          <div className="w-14 h-14 sm:w-16 sm:h-16 rounded-2xl bg-gradient-to-tr from-violet-600/30 to-cyan-500/30 border border-violet-500/30 flex items-center justify-center mb-3 sm:mb-4 shadow-inner pointer-events-none">
            {selectedFile ? (
              isCurrentFileVideo ? (
                <Film className="w-7 h-7 sm:w-8 sm:h-8 text-cyan-400" />
              ) : (
                <FileAudio className="w-7 h-7 sm:w-8 sm:h-8 text-violet-400" />
              )
            ) : (
              <UploadCloud className="w-7 h-7 sm:w-8 sm:h-8 text-violet-400" />
            )}
          </div>

          {selectedFile ? (
            <div className="space-y-3 relative z-30 w-full max-w-md">
              <h3 className="text-base sm:text-lg font-semibold text-white tracking-tight break-all">
                {selectedFile.name}
              </h3>
              <div className="flex flex-wrap items-center justify-center gap-2">
                <span className="text-xs text-gray-400">
                  {(selectedFile.size / (1024 * 1024)).toFixed(1)} MB
                </span>
                {isCurrentFileVideo ? (
                  <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">
                    <Film className="w-3 h-3" /> Video Audio
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-violet-500/20 text-violet-300 border border-violet-500/30">
                    Audio File
                  </span>
                )}
              </div>
              <div>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    setSelectedFile(null);
                    if (fileInputRef.current) {
                      fileInputRef.current.value = '';
                    }
                  }}
                  className="text-xs text-violet-400 hover:text-violet-300 underline pt-1 cursor-pointer"
                >
                  Choose a different file
                </button>
              </div>
            </div>
          ) : (
            <div className="space-y-2 pointer-events-none">
              <h3 className="text-lg sm:text-xl font-semibold text-white tracking-tight">
                Select your Audio or Video file
              </h3>
              <p className="text-xs sm:text-sm text-gray-400 max-w-md mx-auto">
                Drag and drop here, or tap below to browse from your device
              </p>
              <div className="pt-2 flex flex-wrap items-center justify-center gap-2.5">
                <span className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-violet-600 text-white text-xs sm:text-sm font-semibold shadow-md shadow-violet-600/20 pointer-events-auto cursor-pointer">
                  <Video className="w-4 h-4" />
                  <Music className="w-4 h-4" />
                  <span>Choose File</span>
                </span>
                <button
                  type="button"
                  onClick={async (e) => {
                    e.stopPropagation();
                    e.preventDefault();
                    try {
                      const res = await fetch('/sample_song.wav');
                      const blob = await res.blob();
                      const file = new File([blob], 'demo_sample.wav', { type: 'audio/wav' });
                      handleFileSelected(file);
                    } catch (err) {
                      console.error(err);
                    }
                  }}
                  className="pointer-events-auto relative z-30 inline-flex items-center gap-1.5 px-3.5 py-2.5 rounded-xl bg-cyan-950/30 hover:bg-cyan-900/40 text-cyan-300 border border-cyan-500/30 text-xs font-medium transition cursor-pointer"
                  title="Try a sample audio file"
                >
                  <Sparkles className="w-3.5 h-3.5 text-cyan-400" />
                  <span>Try Sample Audio</span>
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Error Message */}
      {error && (
        <div className="flex items-center gap-3 p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-sm">
          <AlertCircle className="w-5 h-5 flex-shrink-0 text-rose-400" />
          <span>{error}</span>
        </div>
      )}

      {/* Action Card */}
      {selectedFile && (
        <div className="p-4 sm:p-5 rounded-2xl bg-[#121622] border border-[#1f2738] space-y-4">
          <div className="flex items-center gap-3 p-3.5 rounded-xl bg-emerald-950/20 border border-emerald-500/30 text-emerald-300">
            <CheckCircle2 className="w-5 h-5 text-emerald-400 flex-shrink-0" />
            <div>
              <h4 className="font-semibold text-white text-sm">AI Speech Disentanglement & Lyric Removal</h4>
              <p className="text-xs text-gray-400 mt-0.5">
                Isolates clean Foreground Speech with background songs and singing lyrics completely removed.
              </p>
            </div>
          </div>

          {/* Upload Progress Bar */}
          {isUploading && (
            <div className="space-y-1.5 pt-1">
              <div className="flex justify-between text-xs text-gray-400">
                <span>Uploading...</span>
                <span>{uploadPercent}%</span>
              </div>
              <div className="w-full h-2 rounded-full bg-[#1a2232] overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-violet-500 to-cyan-500 transition-all duration-200"
                  style={{ width: `${uploadPercent}%` }}
                />
              </div>
            </div>
          )}

          {/* Action Button */}
          <div className="flex justify-end pt-1">
            <button
              onClick={handleStartSeparation}
              disabled={isUploading}
              className={`w-full sm:w-auto flex items-center justify-center gap-2 px-6 sm:px-8 py-3 rounded-xl font-semibold text-sm transition shadow-lg ${
                isUploading
                  ? 'bg-violet-900/50 text-violet-300 cursor-not-allowed'
                  : 'bg-gradient-to-r from-violet-600 to-indigo-600 text-white hover:from-violet-500 hover:to-indigo-500 shadow-violet-600/25 active:scale-[0.98] cursor-pointer'
              }`}
            >
              <Wand2 className={`w-4 h-4 ${isUploading ? 'animate-spin' : ''}`} />
              <span>{isUploading ? 'Uploading & Processing...' : 'Separate Speech & Music'}</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
