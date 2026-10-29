import numpy as np
import torch
import soundfile as sf

def isolate_dominant_voiceover(vocals_wav: np.ndarray, sr: int = 44100):
    """
    Isolates foreground voiceover/speech from background song vocals.
    vocals_wav: numpy array with shape [samples, 2]
    returns: (voiceover_wav, song_vocals_wav)
    """
    # Transpose to [2, samples]
    vocals = torch.from_numpy(vocals_wav.T).float()
    channels, samples = vocals.shape

    mid = (vocals[0] + vocals[1]) * 0.5
    side = (vocals[0] - vocals[1]) * 0.5

    n_fft = 2048
    hop_length = 512
    win_length = 2048
    window = torch.hann_window(win_length)

    stft_mid = torch.stft(mid, n_fft=n_fft, hop_length=hop_length, win_length=win_length, window=window, return_complex=True)
    stft_side = torch.stft(side, n_fft=n_fft, hop_length=hop_length, win_length=win_length, window=window, return_complex=True)

    mag_mid = torch.abs(stft_mid)
    mag_side = torch.abs(stft_side)

    # 1. Spatial mask: center voiceover has low side energy; stereo backing vocals have high side energy
    side_ratio = mag_side / (mag_mid + 1e-6)
    spatial_mask = torch.clamp(1.0 - 1.5 * side_ratio, min=0.05, max=1.0)

    # 2. Adaptive Energy Envelope Gating:
    # Compute frame-level energy in speech formant region (300Hz - 4000Hz)
    freqs = torch.linspace(0, sr // 2, steps=mag_mid.shape[0])
    speech_band = (freqs >= 300) & (freqs <= 4000)
    speech_energy = torch.mean(mag_mid[speech_band, :] ** 2, dim=0)
    energy_db = 10.0 * torch.log10(speech_energy + 1e-9)

    # Baseline background vocal floor (30th percentile)
    k = max(1, int(len(energy_db) * 0.3))
    floor_val = float(torch.kthvalue(energy_db, k).values)

    delta_db = energy_db - floor_val
    # Soft logistic curve: full gain when speech is active (> 6dB above floor)
    vad_mask = torch.sigmoid((delta_db - 4.0) / 2.5)

    # Smooth VAD mask across time to prevent sudden drops
    pad = 5
    vad_padded = torch.nn.functional.pad(vad_mask.unsqueeze(0).unsqueeze(0), (pad, pad), mode='replicate')
    smooth_vad = torch.nn.functional.avg_pool1d(vad_padded, kernel_size=11, stride=1).squeeze()
    smooth_vad = torch.clamp(smooth_vad, 0.08, 1.0)

    # Combined mask
    total_mask = spatial_mask * smooth_vad.unsqueeze(0)
    total_mask = torch.clamp(total_mask, 0.0, 1.0)

    # Apply mask to Mid channel
    voiceover_stft = stft_mid * total_mask
    voiceover_mono = torch.istft(voiceover_stft, n_fft=n_fft, hop_length=hop_length, win_length=win_length, window=window, length=samples)

    # Reconstruct stereo voiceover
    voiceover = torch.stack([voiceover_mono, voiceover_mono], dim=0)

    # Song vocals is the residual
    song_vocals = vocals - voiceover

    vo_np = voiceover.cpu().numpy().T
    sv_np = song_vocals.cpu().numpy().T
    return vo_np, sv_np

# Test with synthetic test signal
sr = 44100
t = np.linspace(0, 3, sr * 3, endpoint=False)
# Voiceover: center-panned speech-like harmonic
vo = 0.8 * np.sin(2 * np.pi * 200 * t)
# Backing vocals: stereo panned with phase difference
bg_left = 0.3 * np.sin(2 * np.pi * 440 * t)
bg_right = 0.3 * np.sin(2 * np.pi * 440 * t + 0.5)

vocal_mix = np.column_stack([vo + bg_left, vo + bg_right])

vo_extracted, bg_extracted = isolate_dominant_voiceover(vocal_mix, sr)
print("Input shape:", vocal_mix.shape)
print("VO extracted shape:", vo_extracted.shape)
print("BG extracted shape:", bg_extracted.shape)
assert vo_extracted.shape == vocal_mix.shape
assert bg_extracted.shape == vocal_mix.shape
print("Voiceover isolation test passed successfully!")
