import pytest
from pathlib import Path
from app.services.audio_validator import AudioValidator, AudioValidationError
from scripts.create_test_audio import generate_test_song

@pytest.fixture(scope="session")
def test_audio_file(tmp_path_factory):
    fn = tmp_path_factory.mktemp("audio") / "sample.wav"
    generate_test_song(output_path=str(fn), duration_sec=2.0)
    return fn

def test_verify_magic_bytes_valid_wav(test_audio_file):
    assert AudioValidator.verify_magic_bytes(test_audio_file) is True

def test_verify_magic_bytes_corrupt_file(tmp_path):
    corrupt = tmp_path / "corrupt.wav"
    corrupt.write_bytes(b"NOT_A_VALID_HEADER_DATA")
    # Validator inspect will reject corrupt media
    with pytest.raises(AudioValidationError):
        AudioValidator.inspect_audio(corrupt)

def test_inspect_audio_valid_metadata(test_audio_file):
    metadata = AudioValidator.inspect_audio(test_audio_file)
    assert metadata["duration_seconds"] > 1.5
    assert metadata["sample_rate"] == 44100
    assert metadata["channels"] == 2
    assert metadata["format"] == "wav"
    assert metadata["file_size_bytes"] > 0

def test_file_not_found():
    non_existent = Path("does_not_exist.wav")
    with pytest.raises(AudioValidationError) as exc:
        AudioValidator.inspect_audio(non_existent)
    assert exc.value.code == "FILE_NOT_FOUND"
