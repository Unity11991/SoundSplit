# StemLab AI — Model Architecture & Weights Guide

## Supported Models

StemLab AI integrates **Demucs v4 (Hybrid Transformer Demucs - `htdemucs`)**, developed by Alexandre Défossez et al. at Meta AI Research.

### Model Details
- **Architecture**: Dual-domain Hybrid Transformer operating jointly on raw audio waveforms and complex time-frequency spectrograms (STFT).
- **Default Checkpoint**: `htdemucs` (4 source stems: `drums`, `bass`, `other`, `vocals`).
- **Sample Rate**: 44,100 Hz stereo.
- **Inference Footprint**:
  - GPU: ~2.2 GB VRAM with 8.0s segment chunking.
  - CPU: ~3.8 GB RAM with 4 execution threads.

### Stem Modes
1. **Two-Stem Mode (`two_stem`)**:
   - `vocals.wav`: Extracted vocal harmonics.
   - `instrumental.wav`: Complete instrumental backing track reconstructed by summing `drums + bass + other` from the model's actual separation output.
2. **Four-Stem Mode (`four_stem`)**:
   - `vocals.wav`: Isolated vocal track.
   - `drums.wav`: Isolated kick, snare, cymbals, percussion.
   - `bass.wav`: Isolated bass guitar and sub-bass synthesizers.
   - `other.wav`: Isolated guitars, pianos, synthesizers, and auxiliary instruments.

## Licensing & Terms of Use

- **Demucs License**: The Demucs architecture and pre-trained models are distributed under the **MIT License**.
- **Commercial Usage**: Permitted under MIT terms, subject to copyright compliance with uploaded user audio.
- **Audio Rights**: Users must possess necessary rights or permissions for audio files uploaded for processing.
