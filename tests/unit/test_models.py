import pytest
import numpy as np
import torch
from apps.worker.engine.demucs_adapter import DemucsModelAdapter

def test_demucs_adapter_initialization():
    adapter = DemucsModelAdapter(model_name="htdemucs")
    assert adapter.name == "htdemucs"
    assert "two_stem" in adapter.supported_modes
    assert "four_stem" in adapter.supported_modes

def test_audio_normalization():
    # Signal exceeding 0.95
    loud_signal = np.array([1.5, -1.8, 0.5, -0.2], dtype=np.float32)
    normalized = DemucsModelAdapter._normalize_audio(loud_signal)
    assert np.max(np.abs(normalized)) <= 0.951

def test_generate_waveform_peaks():
    signal = np.sin(np.linspace(0, 10, 1000)).astype(np.float32)
    stereo = np.vstack([signal, signal])
    peaks = DemucsModelAdapter._generate_waveform_peaks(stereo, num_points=50)
    assert len(peaks) == 50
    assert all(0.0 <= p <= 1.0 for p in peaks)

def test_device_determination():
    adapter = DemucsModelAdapter()
    cpu_device = adapter._determine_device(preferred_device="cpu")
    assert cpu_device.type == "cpu"
