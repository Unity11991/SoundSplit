import pytest
import time
from pathlib import Path
from fastapi import HTTPException
from app.services.storage import StorageService

def test_safe_path_resolution(tmp_path):
    storage = StorageService(base_dir=str(tmp_path))
    safe_path = storage._resolve_safe_path("inputs/my_audio.wav")
    assert str(safe_path).startswith(str(tmp_path.resolve()))

def test_path_traversal_rejection(tmp_path):
    storage = StorageService(base_dir=str(tmp_path))
    with pytest.raises(HTTPException) as excinfo:
        storage._resolve_safe_path("../../../secret.txt")
    assert excinfo.value.status_code == 400
    assert "Path traversal" in excinfo.value.detail

def test_signed_token_lifecycle(tmp_path):
    storage = StorageService(base_dir=str(tmp_path))
    key = "outputs/job123/vocals.wav"
    token = storage.generate_signed_token(key, expires_in=10)
    
    # Valid token verification
    assert storage.verify_signed_token(key, token) is True
    
    # Wrong key verification
    assert storage.verify_signed_token("outputs/job123/drums.wav", token) is False
    
    # Expired token verification
    expired_token = storage.generate_signed_token(key, expires_in=-1)
    assert storage.verify_signed_token(key, expired_token) is False

def test_unicode_stem_filename_and_headers(tmp_path):
    import urllib.parse
    from starlette.responses import FileResponse
    from app.api.v1.endpoints.stems import _sanitize_filename

    # Create dummy file
    dummy_wav = tmp_path / "vocals.wav"
    dummy_wav.write_bytes(b"RIFF dummy wav data")

    # International song titles (Japanese, Hindi, emojis, accents)
    test_titles = [
        "あらゆる追いかけっこを繰り広げる (1)",
        "तेरे वास्ते फलक से",
        "Canción del Mariachi",
        "🎵🔥 Heavy Bass",
    ]

    for title in test_titles:
        utf8_fn, ascii_fn = _sanitize_filename(title, "vocals", "mp3")
        
        # Verify ascii_fn contains ONLY valid ASCII characters
        assert all(32 <= ord(c) <= 126 for c in ascii_fn)
        assert '"' not in ascii_fn
        assert '\\' not in ascii_fn
        
        # Verify Content-Disposition can be encoded to latin-1 by Starlette without throwing UnicodeEncodeError
        quoted = urllib.parse.quote(utf8_fn, encoding="utf-8")
        cd_header = f'attachment; filename="{ascii_fn}"; filename*=UTF-8\'\'{quoted}'
        
        resp = FileResponse(
            path=dummy_wav,
            media_type="audio/mpeg",
            headers={"Content-Disposition": cd_header}
        )
        assert resp.status_code == 200
        # Check raw headers were encoded without exception
        raw_cd = dict(resp.raw_headers).get(b'content-disposition')
        assert raw_cd is not None
        assert b"filename*=" in raw_cd

