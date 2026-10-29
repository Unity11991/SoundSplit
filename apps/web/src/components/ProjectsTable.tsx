'use client';

import React, { useEffect, useState } from 'react';
import { Folder, Trash2, ExternalLink, Archive, Clock, Music, Disc3, RefreshCw } from 'lucide-react';
import { ProjectListItem } from '@/types';
import { listProjects, deleteProject } from '@/lib/api';

interface ProjectsTableProps {
  onOpenProject?: (projectId: string) => void;
}

export default function ProjectsTable({ onOpenProject }: ProjectsTableProps) {
  const [projects, setProjects] = useState<ProjectListItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);

  const fetchProjects = async (p = 1) => {
    setIsLoading(true);
    try {
      const data = await listProjects(p, 10);
      setProjects(data.items);
      setTotal(data.total);
      setPage(data.page);
    } catch (e) {
      console.error('Failed to load projects:', e);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchProjects(page);
  }, [page]);

  const handleDelete = async (id: string, name: string) => {
    if (!confirm(`Are you sure you want to delete project "${name}" and all its audio files?`)) {
      return;
    }
    try {
      await deleteProject(id);
      fetchProjects(page);
    } catch (e: any) {
      alert(e.message || 'Failed to delete project');
    }
  };

  const formatDuration = (secs: number) => {
    const m = Math.floor(secs / 60);
    const s = Math.floor(secs % 60);
    return `${m}:${s < 10 ? '0' : ''}${s}`;
  };

  const formatDate = (iso: string) => {
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  };

  return (
    <div className="w-full max-w-5xl mx-auto space-y-4">
      <div className="flex items-center justify-between pb-2">
        <div className="flex items-center gap-2">
          <Folder className="w-5 h-5 text-violet-400" />
          <h2 className="text-xl font-bold text-white tracking-tight">Your Audio Projects</h2>
          <span className="text-xs px-2 py-0.5 rounded-full bg-[#181e2c] text-gray-400 border border-[#263045] font-mono">
            {total} Total
          </span>
        </div>
        <button
          onClick={() => fetchProjects(page)}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#141924] hover:bg-[#1a2232] text-xs font-mono text-gray-300 border border-[#263045] transition"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
          <span>Refresh</span>
        </button>
      </div>

      {isLoading ? (
        <div className="p-12 text-center rounded-2xl bg-[#121622] border border-[#1f2738] space-y-3">
          <div className="w-8 h-8 rounded-full border-2 border-violet-500 border-t-transparent animate-spin mx-auto" />
          <p className="text-sm text-gray-400 font-mono">Loading projects...</p>
        </div>
      ) : projects.length === 0 ? (
        <div className="p-16 text-center rounded-2xl bg-[#121622] border border-[#1f2738] space-y-4">
          <div className="w-14 h-14 rounded-2xl bg-[#181e2c] border border-[#263045] flex items-center justify-center mx-auto text-gray-500">
            <Music className="w-7 h-7" />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-white">No projects found yet</h3>
            <p className="text-sm text-gray-400 max-w-sm mx-auto mt-1">
              Upload your first track in the Studio to generate vocals, drums, bass, and instrumental stems.
            </p>
          </div>
        </div>
      ) : (
        <div className="rounded-2xl bg-[#121622] border border-[#1f2738] overflow-hidden shadow-xl">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-[#0b0d13] text-gray-400 text-xs font-mono border-b border-[#1f2738]">
                <tr>
                  <th className="px-6 py-3.5 font-medium">Project Name</th>
                  <th className="px-6 py-3.5 font-medium">Duration</th>
                  <th className="px-6 py-3.5 font-medium">Separations</th>
                  <th className="px-6 py-3.5 font-medium">Status</th>
                  <th className="px-6 py-3.5 font-medium">Date</th>
                  <th className="px-6 py-3.5 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#1a2232]">
                {projects.map((proj) => (
                  <tr key={proj.id} className="hover:bg-[#151a28] transition group">
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-3">
                        <div className="w-9 h-9 rounded-lg bg-violet-600/20 border border-violet-500/30 flex items-center justify-center text-violet-400">
                          <Disc3 className="w-4 h-4" />
                        </div>
                        <div>
                          <p className="font-semibold text-white group-hover:text-violet-300 transition">
                            {proj.name}
                          </p>
                          <p className="text-xs text-gray-400 font-mono">{proj.original_filename}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4 font-mono text-xs text-gray-300">
                      <div className="flex items-center gap-1.5">
                        <Clock className="w-3.5 h-3.5 text-gray-500" />
                        <span>{formatDuration(proj.duration_seconds)}</span>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <span className="text-xs font-mono px-2 py-0.5 rounded bg-violet-500/15 text-violet-300 border border-violet-500/20">
                        {proj.latest_separation_mode === 'four_stem' ? '4 Stems' : '2 Stems'}
                      </span>
                    </td>
                    <td className="px-6 py-4 font-mono text-xs">
                      <span
                        className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium ${
                          proj.status === 'completed'
                            ? 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30'
                            : proj.status === 'processing'
                            ? 'bg-amber-500/15 text-amber-300 border border-amber-500/30 animate-pulse'
                            : 'bg-gray-800 text-gray-300'
                        }`}
                      >
                        {proj.status.toUpperCase()}
                      </span>
                    </td>
                    <td className="px-6 py-4 font-mono text-xs text-gray-400">{formatDate(proj.created_at)}</td>
                    <td className="px-6 py-4 text-right">
                      <div className="flex items-center justify-end gap-2">
                        {onOpenProject && (
                          <button
                            onClick={() => onOpenProject(proj.id)}
                            className="p-2 rounded-lg bg-[#181e2c] hover:bg-violet-600/20 text-gray-300 hover:text-violet-300 transition border border-[#263045]"
                            title="Open Project Mixer"
                          >
                            <ExternalLink className="w-4 h-4" />
                          </button>
                        )}
                        <button
                          onClick={() => handleDelete(proj.id, proj.name)}
                          className="p-2 rounded-lg bg-[#181e2c] hover:bg-rose-600/20 text-gray-300 hover:text-rose-400 transition border border-[#263045]"
                          title="Delete Project"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
