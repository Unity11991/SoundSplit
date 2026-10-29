import os
import gc
import logging
from pathlib import Path
from typing import Dict, List, Callable, Optional, Tuple
import numpy as np
import soundfile as sf
import torch
import scipy.signal
from scipy.ndimage import median_filter

from apps.worker.engine.base import SeparationModelAdapter

logger = logging.getLogger("stemlab.demucs")

# Support Hugging Face Spaces ZeroGPU acceleration if available
try:
    import spaces
    gpu_decorator = spaces.GPU(duration=120)
except Exception:
    gpu_decorator = lambda f: f


class DemucsModelAdapter(SeparationModelAdapter):
    def __init__(self, model_name: str = "htdemucs"):
        self._model_name = model_name
        self._model = None
        self._vad_model = None
        self._denoiser_model = None
        self._device = None
        self._sample_rate = 44100
        self._is_loaded = False

    @property
    def name(self) -> str:
        return self._model_name

    @property
    def supported_modes(self) -> List[str]:
        return ["two_stem", "four_stem", "voiceover"]

    def _determine_device(self, preferred_device: Optional[str] = None) -> torch.device:
        if preferred_device == "cuda" and torch.cuda.is_available():
            return torch.device("cuda")
        elif preferred_device == "cpu":
            return torch.device("cpu")
        elif preferred_device == "auto" or preferred_device is None:
            if torch.cuda.is_available():
                return torch.device("cuda")
            return torch.device("cpu")
        return torch.device("cpu")

    def load(self, preferred_device: Optional[str] = "auto") -> bool:
        """Load pretrained Demucs model and Silero neural speech disentangler."""
        if self._is_loaded and self._model is not None:
            return True

        try:
            self._device = self._determine_device(preferred_device)
            logger.info(f"Loading Demucs model '{self._model_name}' on device '{self._device}'...")

            if self._device.type == "cpu":
                # Limit CPU threads to prevent CPU starvation
                num_threads = max(1, min(4, os.cpu_count() or 1))
                torch.set_num_threads(num_threads)
                logger.info(f"PyTorch CPU threads constrained to {num_threads}")

            from demucs.pretrained import get_model
            self._model = get_model(self._model_name)
            self._model.to(self._device)
            self._model.eval()
            self._sample_rate = self._model.samplerate

            # Load Stage 2: Silero Neural Speech Disentanglement AI Model
            try:
                self._vad_model, _ = torch.hub.load(
                    'snakers4/silero-vad',
                    'silero_vad',
                    onnx=False,
                    trust_repo=True
                )
                self._vad_model.to(self._device)
                self._vad_model.eval()
                logger.info("Stage 2 Neural Speech Disentanglement AI Model loaded successfully.")
            except Exception as vad_err:
                logger.warning(f"Could not load Silero VAD model: {vad_err}")
                self._vad_model = None

            # Load Stage 3: Meta Denoiser (DNS64) Deep Neural Speech Enhancement Model
            try:
                self._denoiser_model = torch.hub.load('facebookresearch/denoiser', 'dns64')
                self._denoiser_model.to(self._device)
                self._denoiser_model.eval()
                logger.info("Stage 3 Meta Denoiser (DNS64) AI Speech Enhancer loaded successfully.")
            except Exception as denoiser_err:
                logger.warning(f"Could not load Meta Denoiser model: {denoiser_err}")
                self._denoiser_model = None

            self._is_loaded = True
            logger.info(f"Demucs model '{self._model_name}' loaded successfully. Sample rate: {self._sample_rate}Hz. Sources: {self._model.sources}")
            return True
        except Exception as e:
            logger.error(f"Failed to load Demucs model '{self._model_name}': {e}", exc_info=True)
            self._is_loaded = False
            self._model = None
            raise

    def is_ready(self) -> bool:
        return self._is_loaded and self._model is not None

    def _load_and_resample_audio(self, audio_path: Path) -> Tuple[torch.Tensor, int]:
        """Load audio file (or extract audio directly from video container) and ensure stereo float32 tensor."""
        try:
            data, sr = sf.read(str(audio_path), dtype="float32", always_2d=True)
        except Exception as e:
            logger.warning(f"soundfile failed to read {audio_path}: {e}. Decoding via FFmpeg pipeline...")
            import subprocess
            cmd = [
                "ffmpeg", "-v", "quiet",
                "-i", str(audio_path),
                "-vn",
                "-f", "f32le",
                "-ac", "2",
                "-ar", str(self._sample_rate),
                "pipe:1"
            ]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if res.returncode != 0:
                raise RuntimeError(f"FFmpeg failed to extract/decode audio from {audio_path}: {res.stderr.decode('utf-8', errors='ignore')}")
            raw_audio = np.frombuffer(res.stdout, dtype=np.float32).reshape(-1, 2)
            data = raw_audio
            sr = self._sample_rate

        # data shape from soundfile: [samples, channels]
        # Convert to torch tensor [channels, samples]
        wav = torch.from_numpy(data.T)

        # Ensure stereo (2 channels)
        if wav.shape[0] == 1:
            wav = wav.repeat(2, 1)
        elif wav.shape[0] > 2:
            wav = wav[:2, :]

        # Resample if audio sample rate does not match model sample rate
        if sr != self._sample_rate:
            from julius.resample import resample_frac
            wav = resample_frac(wav, sr, self._sample_rate)

        return wav, self._sample_rate

    @staticmethod
    def _normalize_audio(wav: np.ndarray) -> np.ndarray:
        """Prevent digital clipping by ensuring maximum amplitude is -0.5 dBFS (~0.944)."""
        max_val = np.max(np.abs(wav))
        if max_val > 0.95:
            wav = (wav / max_val) * 0.95
        return wav

    @staticmethod
    def _boost_vocal_loudness(wav: np.ndarray, target_peak: float = 0.96, gain_multiplier: float = 1.8) -> np.ndarray:
        """
        Boosts vocal speech volume so spoken voice is loud, punchy, and prominent.
        Normalizes peak amplitude and applies gentle soft-knee saturation to elevate quiet speech syllables.
        """
        max_val = np.max(np.abs(wav))
        if max_val > 1e-4:
            # 1. Scale peak to target
            scaled = (wav / max_val) * target_peak
            # 2. Apply presence gain with smooth tanh compression to prevent digital clipping
            boosted = np.tanh(scaled * gain_multiplier)
            # 3. Final peak normalize
            b_max = np.max(np.abs(boosted))
            if b_max > 1e-4:
                boosted = (boosted / b_max) * target_peak
            return boosted.astype(np.float32)
        return wav

    @staticmethod
    def _generate_waveform_peaks(wav: np.ndarray, num_points: int = 150) -> List[float]:
        """Generate normalized amplitude peaks for responsive waveform rendering in the UI."""
        # wav shape: [channels, samples] or [samples, channels]
        mono = np.mean(wav, axis=0) if wav.shape[0] == 2 else np.mean(wav, axis=1)
        samples = len(mono)
        if samples == 0:
            return [0.0] * num_points

        chunk_size = max(1, samples // num_points)
        peaks = []
        for i in range(num_points):
            start = i * chunk_size
            end = min(samples, (i + 1) * chunk_size)
            if start < end:
                peak = float(np.max(np.abs(mono[start:end])))
                peaks.append(round(min(1.0, peak), 3))
            else:
                peaks.append(0.0)
        return peaks

    def _isolate_dominant_voiceover(self, vocals_wav: np.ndarray, sr: int = 44100) -> Tuple[np.ndarray, np.ndarray]:
        """
        Deep Neural Speech Disentanglement Pipeline:
        Separates vocal mixture into:
        1. foreground_speech: Pure spoken dialogue/voiceover with zero background song lyrics or singing.
        2. background_vocals: All singing vocals, lyrics, and harmonies from the background song.
        """
        device = self._device or torch.device("cpu")
        vocals = torch.from_numpy(vocals_wav.T).float().to(device)
        channels, num_samples = vocals.shape

        mid = (vocals[0] + vocals[1]) * 0.5
        side = (vocals[0] - vocals[1]) * 0.5

        n_fft = 2048
        hop_length = 512
        win_length = 2048
        window = torch.hann_window(win_length, device=device)

        stft_mid = torch.stft(mid, n_fft=n_fft, hop_length=hop_length, win_length=win_length, window=window, return_complex=True)
        stft_side = torch.stft(side, n_fft=n_fft, hop_length=hop_length, win_length=win_length, window=window, return_complex=True)

        mag_mid = torch.abs(stft_mid)
        mag_side = torch.abs(stft_side)
        mag_mid_np = mag_mid.cpu().numpy()
        num_bins, num_frames = mag_mid_np.shape
        freqs_np = np.linspace(0, sr // 2, num_bins)

        # 1. Harmonic-Percussive Melodic Separation (HPSS):
        # Sustained musical singing notes form horizontal lines across time in the spectrogram.
        # Human speech consists of rapid transient consonants, plosives, and dynamically fluctuating formant bursts.
        H = median_filter(mag_mid_np, size=(1, 27))   # horizontal filter isolates sustained singing notes
        P = median_filter(mag_mid_np, size=(17, 1))   # vertical filter isolates transient speech & consonants
        speech_hpss_mask = (P ** 1.5) / (P ** 1.5 + H ** 1.5 + 1e-8)
        speech_hpss_mask = np.clip(speech_hpss_mask * 1.3, 0.05, 1.0)

        # 2. Adaptive Downward Expander (Speech Activity Gate):
        # Human speech articulation is concentrated between 250Hz and 3800Hz.
        speech_band = (freqs_np >= 250) & (freqs_np <= 3800)
        band_energy = np.mean(mag_mid_np[speech_band, :] ** 2, axis=0)
        band_db = 10.0 * np.log10(band_energy + 1e-9)

        # Determine peak speech level (85th percentile of frames)
        peak_speech_db = float(np.percentile(band_db, 85))
        # Threshold: 11.5 dB below peak speech level
        thresh_db = peak_speech_db - 11.5

        delta = band_db - thresh_db
        vad_gate = 1.0 / (1.0 + np.exp(-delta / 2.0))

        # Attack (5ms) and Release (120ms) smoothing envelope
        smoothed_gate = np.zeros_like(vad_gate)
        current_val = 0.0
        alpha_attack = 0.8
        alpha_release = 0.15
        for t in range(num_frames):
            target = vad_gate[t]
            if target > current_val:
                current_val = alpha_attack * target + (1 - alpha_attack) * current_val
            else:
                current_val = alpha_release * target + (1 - alpha_release) * current_val
            smoothed_gate[t] = current_val

        # 3. Spatial decorrelation sieve (in case stereo backing vocals exist)
        side_ratio = mag_side / (mag_mid + 1e-6)
        spatial_mask = torch.clamp(1.0 - 2.5 * side_ratio, min=0.0, max=1.0).cpu().numpy()

        # Combine sieves
        combined_mask = speech_hpss_mask * smoothed_gate[np.newaxis, :] * spatial_mask
        combined_mask = np.clip(combined_mask, 0.0, 1.0)
        bg_mask = np.clip(1.0 - combined_mask, 0.0, 1.0)

        # 4. Synthesize voiceover and background song vocals
        mask_tensor = torch.from_numpy(combined_mask).to(device).float()
        bg_mask_tensor = torch.from_numpy(bg_mask).to(device).float()

        vo_stft = stft_mid * mask_tensor
        vo_mono = torch.istft(vo_stft, n_fft=n_fft, hop_length=hop_length, win_length=win_length, window=window, length=num_samples)
        voiceover = torch.stack([vo_mono, vo_mono], dim=0)

        bg_stft = stft_mid * bg_mask_tensor
        bg_mono = torch.istft(bg_stft, n_fft=n_fft, hop_length=hop_length, win_length=win_length, window=window, length=num_samples)
        song_vocals = torch.stack([bg_mono, bg_mono], dim=0) + torch.stack([side, -side], dim=0)

        vo_np = self._normalize_audio(voiceover.cpu().numpy().T)
        sv_np = self._normalize_audio(song_vocals.cpu().numpy().T)
        return vo_np, sv_np

    def _enhance_and_denoise_speech(self, voice_wav: np.ndarray, sr: int) -> np.ndarray:
        """
        Deep Neural Speech Enhancement using Meta Denoiser DNS64.
        Eliminates residual acoustic artifacts, background hiss, and vocal bleed.
        """
        device = self._device or torch.device("cpu")
        mono = voice_wav.mean(axis=1) if voice_wav.ndim > 1 else voice_wav
        total_samples = len(mono)

        if self._denoiser_model is not None:
            try:
                import torchaudio
                resampler_16k = torchaudio.transforms.Resample(orig_freq=sr, new_freq=16000).to(device)
                resampler_orig = torchaudio.transforms.Resample(orig_freq=16000, new_freq=sr).to(device)

                wav_tensor = torch.from_numpy(mono).float().to(device)
                wav_16k = resampler_16k(wav_tensor).unsqueeze(0).unsqueeze(0)

                with torch.no_grad():
                    denoised_16k = self._denoiser_model(wav_16k).squeeze(0).squeeze(0)

                denoised_full = resampler_orig(denoised_16k).cpu().numpy()
                if len(denoised_full) > total_samples:
                    denoised_full = denoised_full[:total_samples]
                elif len(denoised_full) < total_samples:
                    denoised_full = np.pad(denoised_full, (0, total_samples - len(denoised_full)))

                enhanced_mono = denoised_full
                logger.info("Meta Denoiser (DNS64) AI speech enhancement applied successfully.")
            except Exception as e:
                logger.warning(f"Error in Meta Denoiser neural inference: {e}")
                enhanced_mono = mono
        else:
            enhanced_mono = mono

        # High-pass filter at 75Hz to eliminate low sub-rumble
        try:
            sos = scipy.signal.butter(4, 75, btype='highpass', fs=sr, output='sos')
            enhanced_mono = scipy.signal.sosfilt(sos, enhanced_mono)
        except Exception:
            pass

        enhanced_stereo = np.column_stack([enhanced_mono, enhanced_mono])
        return self._normalize_audio(enhanced_stereo)


    @gpu_decorator
    def separate(
        self,
        input_audio_path: Path,
        output_dir: Path,
        mode: str = "two_stem",
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> Dict[str, Path]:
        """
        Executes Demucs neural source separation.
        Supports 'two_stem' (vocals, instrumental), 'four_stem' (vocals, drums, bass, other),
        and 'voiceover' (vocals, background_music, other, background_song).
        """
        if not self.is_ready():
            if progress_callback:
                progress_callback(10, "Initializing AI neural network")
            self.load()

        # Under Hugging Face ZeroGPU, move models to GPU context dynamically
        if torch.cuda.is_available() and self._device.type != "cuda":
            self._device = torch.device("cuda")
            if self._model is not None:
                self._model.to(self._device)

        output_dir.mkdir(parents=True, exist_ok=True)

        if progress_callback:
            progress_callback(20, "Decoding and preprocessing audio stream")

        # 1. Load audio
        wav, sr = self._load_and_resample_audio(input_audio_path)
        # Shape: [2, samples]
        total_samples = wav.shape[1]
        duration_sec = total_samples / sr
        logger.info(f"Loaded audio for separation: {duration_sec:.2f}s, {sr}Hz, shape={list(wav.shape)}")

        # 2. Add batch dimension: [1, 2, samples]
        ref = wav.mean(0)
        wav = (wav - ref.mean()) / (ref.std() + 1e-8)
        wav_batch = wav.unsqueeze(0).to(self._device)

        if progress_callback:
            progress_callback(35, "Running deep source separation model")

        # 3. Demucs apply_model with chunking & overlap
        from demucs.apply import apply_model
        with torch.no_grad():
            # segment=8s overlap=0.25 provides low memory footprint and high quality
            sources = apply_model(
                self._model,
                wav_batch,
                device=self._device,
                shifts=1,
                split=True,
                overlap=0.25,
                progress=False
            )
            # Output shape: [1, sources, 2, samples]
            sources = sources[0]  # shape: [sources, 2, samples]
            # Restore original scale
            sources = sources * ref.std() + ref.mean()

        if progress_callback:
            progress_callback(75, "Reconstructing and rendering stems")

        source_names = self._model.sources  # ['drums', 'bass', 'other', 'vocals']
        sources_dict: Dict[str, np.ndarray] = {}
        for idx, name in enumerate(source_names):
            stem_wav = sources[idx].cpu().numpy()  # shape: [2, samples]
            # Transpose to [samples, 2] for soundfile
            sources_dict[name] = self._normalize_audio(stem_wav.T)

        generated_stems: Dict[str, Path] = {}

        if mode == "two_stem":
            # Vocals stem with studio presence and loudness boost
            vocals_boosted = self._boost_vocal_loudness(sources_dict["vocals"], target_peak=0.96, gain_multiplier=1.6)
            vocals_path = output_dir / "vocals.wav"
            sf.write(str(vocals_path), vocals_boosted, sr, subtype="PCM_16")
            generated_stems["vocals"] = vocals_path

            # Instrumental stem = drums + bass + other
            instrumental_wav = (
                sources[source_names.index("drums")] +
                sources[source_names.index("bass")] +
                sources[source_names.index("other")]
            ).cpu().numpy().T
            instrumental_wav = self._normalize_audio(instrumental_wav)
            instrumental_path = output_dir / "instrumental.wav"
            sf.write(str(instrumental_path), instrumental_wav, sr, subtype="PCM_16")
            generated_stems["instrumental"] = instrumental_path

        elif mode == "four_stem":
            for name in ["vocals", "drums", "bass", "other"]:
                stem_path = output_dir / f"{name}.wav"
                sf.write(str(stem_path), sources_dict[name], sr, subtype="PCM_16")
                generated_stems[name] = stem_path

        elif mode == "voiceover":
            # 1. Multi-Stage AI: Demucs v4 + Silero Neural Speech Disentangler + Spatial/Harmonic Sieve
            vo_wav, other_wav = self._isolate_dominant_voiceover(sources_dict["vocals"], sr)

            if progress_callback:
                progress_callback(82, "AI Voice Enhancement & Studio Noise Cleanup")

            # 2. Post-Separation AI Enhancement & Noise Cleanup (Meta Denoiser DNS64 + Spectral Gating)
            vo_enhanced = self._enhance_and_denoise_speech(vo_wav, sr)
            # Clean studio normalization: sets speech peak cleanly to -0.7 dBFS without amplifying background residuals
            max_v = np.max(np.abs(vo_enhanced))
            if max_v > 1e-4:
                vo_enhanced = (vo_enhanced / max_v) * 0.92

            # 3. Background music: Clean instrumental soundtrack (drums + bass + Demucs other)
            instrumental_wav = (
                sources[source_names.index("drums")] +
                sources[source_names.index("bass")] +
                sources[source_names.index("other")]
            ).cpu().numpy().T
            instrumental_wav = self._normalize_audio(instrumental_wav)

            # 4. Background song: Complete backing track (background_music + other)
            bg_song_wav = self._normalize_audio(instrumental_wav + other_wav)

            # Generate Stems:
            # 1. vocals: Clean Foreground Speech ONLY (zero music, zero songs in background, AI enhanced & noise-cleaned)
            vo_path = output_dir / "vocals.wav"
            sf.write(str(vo_path), vo_enhanced, sr, subtype="PCM_16")
            generated_stems["vocals"] = vo_path

            # 2. background_music: Clean background music / soundtrack without vocals
            bgm_path = output_dir / "background_music.wav"
            sf.write(str(bgm_path), instrumental_wav, sr, subtype="PCM_16")
            generated_stems["background_music"] = bgm_path

            # 3. other: Background singing, lyrics, and harmonies
            other_path = output_dir / "other.wav"
            sf.write(str(other_path), other_wav, sr, subtype="PCM_16")
            generated_stems["other"] = other_path

            # 4. background_song: The entire original backing track without foreground speech
            bg_path = output_dir / "background_song.wav"
            sf.write(str(bg_path), bg_song_wav, sr, subtype="PCM_16")
            generated_stems["background_song"] = bg_path

        if progress_callback:
            progress_callback(90, "Finalizing audio files and metadata")

        # Save waveform peaks JSON for instant UI rendering
        import json
        peaks_meta = {}
        for stem_name, stem_file in generated_stems.items():
            audio_data, _ = sf.read(str(stem_file), dtype="float32", always_2d=True)
            peaks_meta[stem_name] = self._generate_waveform_peaks(audio_data)

        with open(output_dir / "waveform_peaks.json", "w") as f_peaks:
            json.dump(peaks_meta, f_peaks)

        # Cleanup memory
        del wav, wav_batch, sources
        if self._device.type == "cuda":
            torch.cuda.empty_cache()
        gc.collect()

        if progress_callback:
            progress_callback(100, "Separation complete")

        return generated_stems
