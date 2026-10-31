export interface TrackState {
  id: string;
  name: string;
  url: string;
  buffer: AudioBuffer | null;
  gainNode: GainNode | null;
  sourceNode: AudioBufferSourceNode | null;
  volume: number; // 0.0 to 1.5 (default 1.0)
  isMuted: boolean;
  isSoloed: boolean;
  isLoading: boolean;
}

export type PlaybackMode = 'stems' | 'original';

export class StemLabAudioEngine {
  private ctx: AudioContext | null = null;
  private masterGain: GainNode | null = null;
  private stemsGain: GainNode | null = null;
  private originalGain: GainNode | null = null;

  private originalBuffer: AudioBuffer | null = null;
  private originalSource: AudioBufferSourceNode | null = null;

  private tracks: Map<string, TrackState> = new Map();
  private mode: PlaybackMode = 'stems';

  private isPlaying = false;
  private startTime = 0;
  private pauseTime = 0;
  private duration = 0;

  private animFrameId: number | null = null;
  private timeListeners: Set<(currentTime: number, duration: number) => void> = new Set();
  private stateListeners: Set<(isPlaying: boolean, mode: PlaybackMode) => void> = new Set();

  private isDestroyed = false;

  constructor() {
    // AudioContext will be initialized on user interaction (first play/load)
  }

  private initContext() {
    if (this.isDestroyed || typeof window === 'undefined') return;

    if (!this.ctx) {
      try {
        const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
        if (!AudioCtx) {
          console.warn('Web Audio API is not supported in this browser environment');
          return;
        }
        this.ctx = new AudioCtx();

        this.masterGain = this.ctx.createGain();
        this.masterGain.gain.setValueAtTime(1.0, this.ctx.currentTime);
        this.masterGain.connect(this.ctx.destination);

        // Separate branch for stems mix
        this.stemsGain = this.ctx.createGain();
        this.stemsGain.gain.setValueAtTime(1.0, this.ctx.currentTime);
        this.stemsGain.connect(this.masterGain);

        // Separate branch for original audio
        this.originalGain = this.ctx.createGain();
        this.originalGain.gain.setValueAtTime(0.0, this.ctx.currentTime);
        this.originalGain.connect(this.masterGain);
      } catch (err) {
        console.error('Failed to initialize AudioContext:', err);
        return;
      }
    }

    if (this.ctx && this.ctx.state === 'suspended') {
      this.ctx.resume().catch(() => {});
    }
  }

  public async loadOriginal(url: string): Promise<void> {
    if (this.isDestroyed) return;
    this.initContext();
    if (!this.ctx) return;

    try {
      const res = await fetch(url);
      if (!res.ok) {
        console.warn(`Failed to fetch original audio from ${url}: status ${res.status}`);
        return;
      }
      const arrayBuffer = await res.arrayBuffer();
      if (this.isDestroyed || !this.ctx || this.ctx.state === 'closed') return;
      this.originalBuffer = await this.ctx.decodeAudioData(arrayBuffer);
      if (this.originalBuffer && this.originalBuffer.duration > this.duration) {
        this.duration = this.originalBuffer.duration;
      }
    } catch (e) {
      if (!this.isDestroyed) {
        console.error('Failed to load original audio buffer:', e);
      }
    }
  }

  public async addStemTrack(id: string, name: string, url: string): Promise<void> {
    if (this.isDestroyed) return;
    this.initContext();
    if (!this.ctx || !this.stemsGain) return;

    const gainNode = this.ctx.createGain();
    gainNode.gain.setValueAtTime(1.0, this.ctx.currentTime);
    gainNode.connect(this.stemsGain);

    const track: TrackState = {
      id,
      name,
      url,
      buffer: null,
      gainNode,
      sourceNode: null,
      volume: 1.0,
      isMuted: false,
      isSoloed: false,
      isLoading: true,
    };
    this.tracks.set(id, track);

    try {
      const res = await fetch(url);
      if (!res.ok) {
        console.warn(`Failed to fetch stem track ${name} from ${url}: status ${res.status}`);
        track.isLoading = false;
        return;
      }
      const arrayBuffer = await res.arrayBuffer();
      if (this.isDestroyed || !this.ctx || this.ctx.state === 'closed') {
        track.isLoading = false;
        return;
      }
      const decoded = await this.ctx.decodeAudioData(arrayBuffer);
      track.buffer = decoded;
      track.isLoading = false;

      if (decoded.duration > this.duration) {
        this.duration = decoded.duration;
      }

      // If user hit Play early, seamlessly start this stem at the current playhead
      if (this.isPlaying && track.gainNode && !track.sourceNode) {
        try {
          const offset = this.getCurrentTime() % (decoded.duration || 1);
          track.sourceNode = this.ctx.createBufferSource();
          track.sourceNode.buffer = decoded;
          track.sourceNode.connect(track.gainNode);
          track.sourceNode.start(0, offset);
        } catch {}
      }
    } catch (e) {
      if (!this.isDestroyed) {
        console.error(`Failed to load stem track ${name}:`, e);
      }
      track.isLoading = false;
    }
  }

  public play() {
    this.initContext();
    if (this.isPlaying) return;

    const offset = this.pauseTime % (this.duration || 1);
    this.startTime = this.ctx!.currentTime - offset;

    // Start Original Source Node
    if (this.originalBuffer) {
      this.originalSource = this.ctx!.createBufferSource();
      this.originalSource.buffer = this.originalBuffer;
      this.originalSource.connect(this.originalGain!);
      this.originalSource.start(0, offset);
    }

    // Start all Stem Source Nodes simultaneously
    for (const track of this.tracks.values()) {
      if (track.buffer && track.gainNode) {
        track.sourceNode = this.ctx!.createBufferSource();
        track.sourceNode.buffer = track.buffer;
        track.sourceNode.connect(track.gainNode);
        track.sourceNode.start(0, offset);
      }
    }

    this.isPlaying = true;
    this.updateGains();
    this.notifyState();
    this.startTimeLoop();
  }

  public pause() {
    if (!this.isPlaying) return;

    this.pauseTime = this.getCurrentTime();
    this.stopSourceNodes();
    this.isPlaying = false;
    this.stopTimeLoop();
    this.notifyState();
  }

  public stop() {
    this.pauseTime = 0;
    this.stopSourceNodes();
    this.isPlaying = false;
    this.stopTimeLoop();
    this.notifyTime(0);
    this.notifyState();
  }

  public seek(timeSeconds: number) {
    const wasPlaying = this.isPlaying;
    if (this.isPlaying) {
      this.pause();
    }
    this.pauseTime = Math.max(0, Math.min(timeSeconds, this.duration));
    this.notifyTime(this.pauseTime);
    if (wasPlaying) {
      this.play();
    }
  }

  private stopSourceNodes() {
    if (this.originalSource) {
      try {
        this.originalSource.stop();
        this.originalSource.disconnect();
      } catch {}
      this.originalSource = null;
    }

    for (const track of this.tracks.values()) {
      if (track.sourceNode) {
        try {
          track.sourceNode.stop();
          track.sourceNode.disconnect();
        } catch {}
        track.sourceNode = null;
      }
    }
  }

  public getCurrentTime(): number {
    if (!this.isPlaying) {
      return this.pauseTime;
    }
    const current = this.ctx!.currentTime - this.startTime;
    if (current >= this.duration && this.duration > 0) {
      this.stop();
      return 0;
    }
    return Math.max(0, current);
  }

  public getDuration(): number {
    return this.duration;
  }

  public setMode(mode: PlaybackMode) {
    this.mode = mode;
    this.updateGains();
    this.notifyState();
  }

  public getMode(): PlaybackMode {
    return this.mode;
  }

  public setTrackVolume(trackId: string, volume: number) {
    const track = this.tracks.get(trackId);
    if (track) {
      track.volume = Math.max(0, Math.min(volume, 2.5));
      this.updateGains();
    }
  }

  public toggleMute(trackId: string) {
    const track = this.tracks.get(trackId);
    if (track) {
      track.isMuted = !track.isMuted;
      this.updateGains();
    }
  }

  public toggleSolo(trackId: string) {
    const track = this.tracks.get(trackId);
    if (track) {
      track.isSoloed = !track.isSoloed;
      this.updateGains();
    }
  }

  public setMasterVolume(vol: number) {
    if (this.masterGain && this.ctx) {
      this.masterGain.gain.setValueAtTime(Math.max(0, Math.min(vol, 1.5)), this.ctx.currentTime);
    }
  }

  private updateGains() {
    if (!this.ctx || !this.stemsGain || !this.originalGain) return;

    const now = this.ctx.currentTime;

    // A/B crossfade between original audio and stems mix
    if (this.mode === 'original') {
      this.stemsGain.gain.setTargetAtTime(0.0, now, 0.02);
      this.originalGain.gain.setTargetAtTime(1.0, now, 0.02);
    } else {
      this.stemsGain.gain.setTargetAtTime(1.0, now, 0.02);
      this.originalGain.gain.setTargetAtTime(0.0, now, 0.02);
    }

    // Check if any stem track has Solo enabled
    let anySolo = false;
    for (const t of this.tracks.values()) {
      if (t.isSoloed) {
        anySolo = true;
        break;
      }
    }

    // Apply mute / solo / volume per track
    for (const track of this.tracks.values()) {
      if (!track.gainNode) continue;

      let effectiveGain = 0;
      if (anySolo) {
        effectiveGain = track.isSoloed && !track.isMuted ? track.volume : 0;
      } else {
        effectiveGain = track.isMuted ? 0 : track.volume;
      }

      track.gainNode.gain.setTargetAtTime(effectiveGain, now, 0.02);
    }
  }

  private startTimeLoop() {
    this.stopTimeLoop();
    const update = () => {
      const cur = this.getCurrentTime();
      this.notifyTime(cur);
      if (this.isPlaying) {
        this.animFrameId = requestAnimationFrame(update);
      }
    };
    this.animFrameId = requestAnimationFrame(update);
  }

  private stopTimeLoop() {
    if (this.animFrameId !== null) {
      cancelAnimationFrame(this.animFrameId);
      this.animFrameId = null;
    }
  }

  public onTimeUpdate(cb: (currentTime: number, duration: number) => void): () => void {
    this.timeListeners.add(cb);
    return () => this.timeListeners.delete(cb);
  }

  public onStateChange(cb: (isPlaying: boolean, mode: PlaybackMode) => void): () => void {
    this.stateListeners.add(cb);
    return () => this.stateListeners.delete(cb);
  }

  private notifyTime(time: number) {
    for (const cb of this.timeListeners) {
      cb(time, this.duration);
    }
  }

  private notifyState() {
    for (const cb of this.stateListeners) {
      cb(this.isPlaying, this.mode);
    }
  }

  public getTracks(): TrackState[] {
    return Array.from(this.tracks.values());
  }

  public destroy() {
    this.isDestroyed = true;
    this.stop();
    this.stopSourceNodes();
    this.tracks.clear();
    this.timeListeners.clear();
    this.stateListeners.clear();
    if (this.ctx && this.ctx.state !== 'closed') {
      try {
        this.ctx.close();
      } catch {}
    }
    this.ctx = null;
  }
}
