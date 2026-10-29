import numpy as np
import torch
import torchaudio
import time

def test_multi_stage_speech_isolation():
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Running on device: {device}")

    # Load Silero VAD
    vad_model, _ = torch.hub.load('snakers4/silero-vad', 'silero_vad', onnx=False, trust_repo=True)
    vad_model.to(device)
    vad_model.eval()

    sr = 44100
    duration_sec = 4
    total_samples = sr * duration_sec

    # Synthetic mixture: 
    # 0s - 2s: Song vocal singing "Ahhh" (sustained 440 Hz + harmonics + stereo reverb)
    # 1s - 3s: Speech voiceover (centered, dynamic bursts)
    t = np.linspace(0, duration_sec, total_samples, endpoint=False)
    
    # Background song vocal: stereo with reverb
    song_vocal_l = 0.5 * np.sin(2 * np.pi * 440 * t) + 0.25 * np.sin(2 * np.pi * 880 * t)
    song_vocal_r = 0.5 * np.sin(2 * np.pi * 440 * (t - 0.002)) + 0.25 * np.sin(2 * np.pi * 880 * (t + 0.002))
    
    # Foreground speech: centered, active between 1.0s and 3.0s
    speech_mono = np.zeros_like(t)
    speech_indices = (t >= 1.0) & (t <= 3.0)
    # Speech-like formant bursts
    speech_mono[speech_indices] = (
        0.7 * np.sin(2 * np.pi * 220 * t[speech_indices]) * np.sin(2 * np.pi * 12 * t[speech_indices]) +
        0.3 * np.random.randn(np.sum(speech_indices)) * 0.1
    )

    mix_l = song_vocal_l + speech_mono
    mix_r = song_vocal_r + speech_mono
    vocals_wav = np.column_stack([mix_l, mix_r])

    start_t = time.time()
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
    num_frames = stft_mid.shape[1]

    # 1. Stage 2: Silero VAD Neural Network
    mono_vocals = vocals.mean(dim=0, keepdim=True)
    resampler_16k = torchaudio.transforms.Resample(orig_freq=sr, new_freq=16000).to(device)
    wav_16k = resampler_16k(mono_vocals).squeeze(0)

    chunk_size = 512
    num_chunks = len(wav_16k) // chunk_size
    probs = []
    with torch.no_grad():
        vad_model.reset_states()
        for i in range(num_chunks):
            chunk = wav_16k[i * chunk_size : (i + 1) * chunk_size].unsqueeze(0)
            prob = vad_model(chunk, 16000).item()
            probs.append(prob)

    if len(probs) == 0:
        probs = [1.0]

    prob_tensor = torch.tensor(probs, device=device)
    speech_prob_frames = torch.nn.functional.interpolate(
        prob_tensor.unsqueeze(0).unsqueeze(0),
        size=num_frames,
        mode='linear',
        align_corners=False
    ).squeeze()

    # Dynamic gate with zero bleed during song-only parts
    vad_gate = torch.clamp((speech_prob_frames - 0.25) / 0.35, min=0.0, max=1.0)
    # Smooth over 9 frames (~100ms)
    kernel = torch.ones(1, 1, 9, device=device) / 9.0
    vad_gate_smooth = torch.conv1d(vad_gate.unsqueeze(0).unsqueeze(0), kernel, padding=4).squeeze()
    vad_gate_smooth = torch.clamp(vad_gate_smooth, 0.0, 1.0)

    # 2. Stage 3: Spatial Stereophonic Sieve
    side_ratio = mag_side / (mag_mid + 1e-6)
    spatial_mask = torch.clamp(1.0 - 2.2 * side_ratio, min=0.0, max=1.0)

    # 3. Frequency Envelope (75Hz to 7500Hz)
    freqs = torch.linspace(0, sr // 2, steps=mag_mid.shape[0], device=device)
    freq_weights = torch.ones_like(freqs)
    freq_weights[freqs < 75.0] = torch.clamp(freqs[freqs < 75.0] / 75.0, 0.0, 1.0)
    freq_weights[freqs > 7500.0] = torch.clamp(1.0 - (freqs[freqs > 7500.0] - 7500.0) / 2500.0, 0.0, 1.0)
    freq_mask = freq_weights.unsqueeze(1)  # broadcasts across time frames

    # 4. Harmonic vs Transient Speech Sieve (suppresses sustained melodic singing notes)
    # Average pool along time frames
    mag_padded = torch.nn.functional.pad(mag_mid.unsqueeze(0), (5, 5), mode='replicate')
    sustained_harmonic = torch.nn.functional.avg_pool1d(mag_padded, kernel_size=11, stride=1).squeeze(0)
    harmonic_ratio = sustained_harmonic / (mag_mid + 1e-6)
    harmonic_suppress = torch.clamp(1.0 - 0.5 * torch.clamp(harmonic_ratio - 0.6, 0.0, 1.0), 0.2, 1.0)

    final_speech_mask = spatial_mask * vad_gate_smooth.unsqueeze(0) * freq_mask * harmonic_suppress
    final_speech_mask = torch.clamp(final_speech_mask, 0.0, 1.0)
    bg_mask = torch.clamp(1.0 - final_speech_mask, 0.0, 1.0)

    # Synthesize clean foreground speech
    speech_stft = stft_mid * final_speech_mask
    speech_mono = torch.istft(speech_stft, n_fft=n_fft, hop_length=hop_length, win_length=win_length, window=window, length=num_samples)
    foreground_speech = torch.stack([speech_mono, speech_mono], dim=0)

    bg_stft = stft_mid * bg_mask
    bg_mono = torch.istft(bg_stft, n_fft=n_fft, hop_length=hop_length, win_length=win_length, window=window, length=num_samples)
    bg_vocals = torch.stack([bg_mono, bg_mono], dim=0) + torch.stack([side, -side], dim=0)

    elapsed = time.time() - start_t
    print(f"Multi-Stage AI speech isolation executed in {elapsed:.3f}s")

    fg_np = foreground_speech.cpu().numpy().T
    bg_np = bg_vocals.cpu().numpy().T

    # Verify during 0s - 0.8s (song only, before speech started) that foreground speech is completely silent!
    pre_speech_energy = np.mean(fg_np[:int(0.8 * sr), :] ** 2)
    active_speech_energy = np.mean(fg_np[int(1.5 * sr):int(2.5 * sr), :] ** 2)

    print(f"Pre-speech residual energy: {pre_speech_energy:.8f}")
    print(f"Active speech energy: {active_speech_energy:.8f}")
    snr_db = 10 * np.log10(active_speech_energy / (pre_speech_energy + 1e-12))
    print(f"Attenuation during song-only parts: {snr_db:.1f} dB")
    assert pre_speech_energy < 1e-4, "Foreground speech leaked song during song-only portion!"
    print("SUCCESS: Zero song leakage during non-speech periods!")

if __name__ == "__main__":
    test_multi_stage_speech_isolation()
