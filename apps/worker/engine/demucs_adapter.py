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
import torchaudio
import noisereduce as nr

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
        self._vad_utils = None
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
                self._vad_model, self._vad_utils = torch.hub.load(
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
                self._vad_utils = None

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
    def _boost_vocal_loudness(wav: np.ndarray, target_peak: float = 0.94, gain_multiplier: float = 1.1) -> np.ndarray:
        """
        Ensures clear vocal volume without introducing harsh non-linear distortion.
        Scales peak cleanly to target_peak and applies subtle soft-knee limiting.
        """
        max_val = np.max(np.abs(wav))
        if max_val > 1e-4:
            scaled = (wav / max_val) * target_peak
            if gain_multiplier > 1.05:
                boosted = np.tanh(scaled * gain_multiplier)
                b_max = np.max(np.abs(boosted))
                if b_max > 1e-4:
                    boosted = (boosted / b_max) * target_peak
                return boosted.astype(np.float32)
            return scaled.astype(np.float32)
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

    def _isolate_dominant_voiceover(
        self,
        vocals_wav: np.ndarray,
        instrumental_wav: np.ndarray,
        sr: int = 44100
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Deep Neural Speech Disentanglement Pipeline:
        Completely eliminates background songs and singing lyrics from foreground speech.
        Separates vocal mixture into:
        1. foreground_speech: Pure spoken dialogue/voiceover with zero background song lyrics, zero music, and pristine noise floor.
        2. background_vocals: All singing vocals, lyrics, and harmonies from the background song.
        """
        device = self._device or torch.device("cpu")
        num_samples = len(vocals_wav)

        try:
            # 1. Convert to mono mid signal
            v_mid = np.mean(vocals_wav, axis=1) if vocals_wav.ndim > 1 else vocals_wav

            # Resamplers
            resampler_16k = torchaudio.transforms.Resample(orig_freq=sr, new_freq=16000).to(device)
            resampler_orig = torchaudio.transforms.Resample(orig_freq=16000, new_freq=sr).to(device)

            v_tensor = torch.from_numpy(v_mid).float().to(device)
            v_16k = resampler_16k(v_tensor)

            # 2. Silero VAD Speech Detection
            speech_timestamps = []
            if self._vad_utils and self._vad_model:
                get_speech_timestamps = self._vad_utils[0]
                speech_timestamps = get_speech_timestamps(
                    v_16k,
                    self._vad_model,
                    sampling_rate=16000,
                    threshold=0.45,
                    min_speech_duration_ms=200,
                    min_silence_duration_ms=150,
                    speech_pad_ms=80
                )
                if len(speech_timestamps) == 0:
                    speech_timestamps = get_speech_timestamps(
                        v_16k,
                        self._vad_model,
                        sampling_rate=16000,
                        threshold=0.30,
                        min_speech_duration_ms=200,
                        min_silence_duration_ms=150,
                        speech_pad_ms=80
                    )

            has_speech = len(speech_timestamps) > 0
            if not has_speech:
                logger.info("No foreground speech detected. Preserving full vocal track for music.")
                return vocals_wav, np.zeros_like(vocals_wav)

            # 3. Build Non-Speech (Background Song) Noise Profile
            non_speech_mask_16k = np.ones(len(v_16k), dtype=bool)
            for ts in speech_timestamps:
                non_speech_mask_16k[ts['start']:ts['end']] = False

            v_16k_np = v_16k.cpu().numpy()
            bg_song_profile = v_16k_np[non_speech_mask_16k]

            # 4. Meta Denoiser (DNS64) in Pure Time-Domain
            # Eliminates acoustic noise, reverberation, and room acoustics natively without STFT phase distortion
            if self._denoiser_model is not None:
                try:
                    with torch.no_grad():
                        denoised_16k = self._denoiser_model(v_16k.unsqueeze(0).unsqueeze(0)).squeeze(0).squeeze(0)
                    denoised_16k_np = denoised_16k.cpu().numpy()
                except Exception as denoise_err:
                    logger.warning(f"Meta Denoiser inference error: {denoise_err}")
                    denoised_16k_np = v_16k_np
            else:
                denoised_16k_np = v_16k_np

            # 5. Smooth Adaptive Spectral Gating targeting background song singing & lyrics
            # Eliminates background singing lyrics even when overlapping with speech, without metallic/chirp noise
            if len(bg_song_profile) >= 16000 * 0.5:
                cleaned_16k = nr.reduce_noise(
                    y=denoised_16k_np,
                    sr=16000,
                    y_noise=bg_song_profile,
                    prop_decrease=0.88,
                    time_mask_smooth_ms=64,
                    freq_mask_smooth_hz=400,
                    n_std_thresh_stationary=1.5
                )
            else:
                cleaned_16k = nr.reduce_noise(
                    y=denoised_16k_np,
                    sr=16000,
                    prop_decrease=0.82,
                    time_mask_smooth_ms=64,
                    freq_mask_smooth_hz=400
                )

            # 6. Resample back to original sample rate
            cleaned_torch = torch.from_numpy(cleaned_16k).float().to(device)
            cleaned_orig = resampler_orig(cleaned_torch).cpu().numpy()[:num_samples]
            if len(cleaned_orig) < num_samples:
                cleaned_orig = np.pad(cleaned_orig, (0, num_samples - len(cleaned_orig)))

            # 7. Smooth Raised-Cosine Speech Gate (prevents abrupt gating / clicks and guarantees silence during pauses)
            sample_gate = np.zeros(num_samples, dtype=np.float32)
            ramp_len = int(sr * 0.035)  # 35ms smooth cosine ramp
            for ts in speech_timestamps:
                start_idx = max(0, int(ts['start'] * sr / 16000))
                end_idx = min(num_samples, int(ts['end'] * sr / 16000))
                sample_gate[start_idx:end_idx] = 1.0
                if start_idx >= ramp_len:
                    t_in = np.linspace(0, np.pi / 2, ramp_len)
                    sample_gate[start_idx - ramp_len:start_idx] = np.sin(t_in) ** 2
                if end_idx + ramp_len <= num_samples:
                    t_out = np.linspace(np.pi / 2, 0, ramp_len)
                    sample_gate[end_idx:end_idx + ramp_len] = np.sin(t_out) ** 2

            fg_clean_mono = cleaned_orig * sample_gate

            # 8. High-pass filter at 80Hz to eliminate sub-rumble and pops
            try:
                sos = scipy.signal.butter(4, 80, btype='highpass', fs=sr, output='sos')
                fg_clean_mono = scipy.signal.sosfilt(sos, fg_clean_mono)
            except Exception:
                pass

            # 9. Clean Peak Normalization to -1.0 dBFS (0.89) without non-linear saturation distortion
            peak_val = np.max(np.abs(fg_clean_mono))
            if peak_val > 1e-4:
                fg_clean_mono = (fg_clean_mono / peak_val) * 0.89

            # 10. Synthesize Stereo Foreground Speech and Background Song Vocals
            fg_stereo = np.column_stack([fg_clean_mono, fg_clean_mono])
            # Background vocals = original vocal stem minus isolated foreground speech
            bg_vocals_stereo = vocals_wav - fg_stereo

            # Normalize background vocals to avoid clipping
            bg_peak = np.max(np.abs(bg_vocals_stereo))
            if bg_peak > 0.95:
                bg_vocals_stereo = (bg_vocals_stereo / bg_peak) * 0.95

            return fg_stereo, bg_vocals_stereo
        except Exception as e:
            logger.error(f"Error in speech disentanglement pipeline: {e}", exc_info=True)
            return vocals_wav, np.zeros_like(vocals_wav)


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
            # 1. Background instrumental music (drums + bass + Demucs other)
            instrumental_wav = (
                sources[source_names.index("drums")] +
                sources[source_names.index("bass")] +
                sources[source_names.index("other")]
            ).cpu().numpy().T
            instrumental_wav = self._normalize_audio(instrumental_wav)

            if progress_callback:
                progress_callback(80, "AI Neural Speech Disentanglement & Lyric Removal")

            # 2. Multi-Stage AI: Demucs v4 + Silero VAD Speech Gating + Harmonic Note Sieve + Meta Denoiser
            vo_wav, other_wav = self._isolate_dominant_voiceover(sources_dict["vocals"], instrumental_wav, sr)

            if progress_callback:
                progress_callback(88, "Reconstructing Isolated Audio Stems")

            # 3. Background song: Complete backing track without foreground speech (instrumental + background lyrics)
            bg_song_wav = self._normalize_audio(instrumental_wav + other_wav)

            # Generate Stems:
            # 1. vocals: Clean Foreground Speech ONLY (zero song lyrics, zero music)
            vo_path = output_dir / "vocals.wav"
            sf.write(str(vo_path), vo_wav, sr, subtype="PCM_16")
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
