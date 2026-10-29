import os
import shutil
import uuid
import hmac
import hashlib
import time
from pathlib import Path
from typing import Optional, BinaryIO
from fastapi import HTTPException

from app.core.config import settings

class StorageService:
    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = Path(base_dir or settings.STORAGE_LOCAL_DIR).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        # Create subdirectories for inputs, outputs, and exports
        (self.base_dir / "inputs").mkdir(exist_ok=True)
        (self.base_dir / "outputs").mkdir(exist_ok=True)
        (self.base_dir / "exports").mkdir(exist_ok=True)

    def _resolve_safe_path(self, storage_key: str) -> Path:
        # Prevent path traversal attacks
        clean_key = storage_key.strip().replace("\\", "/").lstrip("/")
        full_path = (self.base_dir / clean_key).resolve()
        
        # Verify the resolved path is strictly within the storage directory
        if not str(full_path).startswith(str(self.base_dir)):
            raise HTTPException(status_code=400, detail="Invalid storage path detected (Path traversal rejected)")
        return full_path

    def save_upload(self, file_obj: BinaryIO, original_filename: str) -> tuple[str, Path, int]:
        ext = Path(original_filename).suffix.lower()
        if not ext:
            ext = ".wav"
        
        unique_id = uuid.uuid4().hex
        safe_filename = f"{unique_id}{ext}"
        storage_key = f"inputs/{safe_filename}"
        target_path = self._resolve_safe_path(storage_key)
        
        file_size = 0
        with open(target_path, "wb") as f_out:
            shutil.copyfileobj(file_obj, f_out)
        
        file_size = target_path.stat().st_size
        return storage_key, target_path, file_size

    def save_bytes(self, data: bytes, relative_subpath: str) -> tuple[str, Path]:
        target_path = self._resolve_safe_path(relative_subpath)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, "wb") as f:
            f.write(data)
        return relative_subpath, target_path

    def get_absolute_path(self, storage_key: str) -> Path:
        return self._resolve_safe_path(storage_key)

    def file_exists(self, storage_key: str) -> bool:
        try:
            path = self._resolve_safe_path(storage_key)
            return path.exists() and path.is_file()
        except Exception:
            return False

    def delete_file(self, storage_key: str) -> bool:
        try:
            path = self._resolve_safe_path(storage_key)
            if path.exists() and path.is_file():
                path.unlink()
                return True
        except Exception:
            pass
        return False

    def delete_directory(self, relative_dir: str) -> bool:
        try:
            dir_path = self._resolve_safe_path(relative_dir)
            if dir_path.exists() and dir_path.is_dir():
                shutil.rmtree(dir_path)
                return True
        except Exception:
            pass
        return False

    def generate_signed_token(self, storage_key: str, expires_in: int = 3600) -> str:
        expiry = int(time.time()) + expires_in
        payload = f"{storage_key}:{expiry}"
        signature = hmac.new(
            settings.SECRET_KEY.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()
        return f"{expiry}:{signature}"

    def verify_signed_token(self, storage_key: str, token: str) -> bool:
        try:
            parts = token.split(":")
            if len(parts) != 2:
                return False
            expiry = int(parts[0])
            provided_sig = parts[1]
            
            if time.time() > expiry:
                return False  # Expired
            
            payload = f"{storage_key}:{expiry}"
            expected_sig = hmac.new(
                settings.SECRET_KEY.encode(),
                payload.encode(),
                hashlib.sha256
            ).hexdigest()
            return hmac.compare_digest(provided_sig, expected_sig)
        except Exception:
            return False

storage_service = StorageService()
