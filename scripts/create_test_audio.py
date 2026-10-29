import numpy as np
import soundfile as sf
from pathlib import Path

def generate_test_song(output_path: str = "tests/fixtures/test_song.wav", duration_sec: float = 4.0, sample_rate: int = 44100):
    """
    Generate a deterministic synthetic multi-track audio fixture with:
    - Melodic vocal lead (440Hz sine wave with vibrato)
    - Rhythmic drum transients (percussive filtered noise bursts)
    - Deep bassline (sawtooth/sub-bass tone at 110Hz)
    """
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    t = np.linspace(0, duration_sec, int(sample_rate * duration_sec), endpoint=False)

    # 1. Vocal lead simulation: 440Hz with 5Hz vibrato and envelope
    vibrato = 5.0 * np.sin(2 * np.pi * 5.0 * t)
    vocal = 0.4 * np.sin(2 * np.pi * (440.0 + vibrato) * t)

    # 2. Bass synth: 110Hz harmonic tone
    bass = 0.35 * (np.sin(2 * np.pi * 110.0 * t) + 0.3 * np.sin(2 * np.pi * 220.0 * t))

    # 3. Drums simulation: rhythmic transients at 120 BPM (every 0.5s)
    drums = np.zeros_like(t)
    beat_samples = int(sample_rate * 0.5)
    for b in range(0, len(t), beat_samples):
        # Kick drum burst
        hit_len = min(int(sample_rate * 0.1), len(t) - b)
        decay = np.exp(-np.linspace(0, 10, hit_len))
        kick = 0.5 * np.sin(2 * np.pi * np.linspace(150, 40, hit_len) * np.linspace(0, 0.1, hit_len)) * decay
        drums[b:b+hit_len] += kick

    # 4. Mix together to stereo
    left = vocal + bass + drums
    right = vocal * 0.9 + bass * 1.1 + drums

    # Normalize mix to -1.0 dBFS (0.89)
    stereo = np.vstack([left, right]).T
    max_amp = np.max(np.abs(stereo))
    if max_amp > 0:
        stereo = (stereo / max_amp) * 0.89

    sf.write(str(out), stereo, sample_rate, subtype="PCM_16")
    print(f"Generated synthetic test audio fixture: {out.resolve()} (Duration: {duration_sec}s, SR: {sample_rate}Hz)")
    return out

if __name__ == "__main__":
    generate_test_song()
