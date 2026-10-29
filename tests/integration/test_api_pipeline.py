import pytest
import io
import os
import zipfile
from fastapi.testclient import TestClient
from pathlib import Path

from app.main import app
from app.core.database import SessionLocal, init_db
from app.models.database import ProjectModel, SeparationModel
from scripts.create_test_audio import generate_test_song
from apps.worker.engine.pipeline import separation_pipeline

@pytest.fixture(scope="session")
def client():
    init_db()
    return TestClient(app)

@pytest.fixture(scope="session")
def sample_wav(tmp_path_factory):
    fn = tmp_path_factory.mktemp("audio_e2e") / "test_track.wav"
    generate_test_song(output_path=str(fn), duration_sec=2.0)
    return fn

def test_health_and_readiness(client):
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"

    res_ready = client.get("/api/v1/readiness")
    assert res_ready.status_code == 200
    data_ready = res_ready.json()
    assert "checks" in data_ready
    assert data_ready["checks"]["ai_engine"]["status"] == "ok"
    assert data_ready["checks"]["database"]["status"] == "ok"

def test_upload_and_separation_e2e(client, sample_wav):
    # 1. Upload audio file
    with open(sample_wav, "rb") as f:
        files = {"file": ("test_track.wav", f, "audio/wav")}
        upload_res = client.post("/api/v1/uploads", files=files)

    assert upload_res.status_code == 201
    upload_data = upload_res.json()
    project_id = upload_data["project_id"]
    assert project_id is not None
    assert upload_data["metadata"]["duration_seconds"] > 1.0

    # 2. Dispatch 2-Stem Separation
    sep_payload = {
        "project_id": project_id,
        "mode": "two_stem",
        "model_name": "htdemucs"
    }
    sep_res = client.post("/api/v1/separations", json=sep_payload)
    assert sep_res.status_code == 201
    sep_data = sep_res.json()
    job_id = sep_data["id"]
    assert sep_data["status"] == "queued"

    # 3. Wait for real asynchronous background worker to complete the AI separation
    import time
    max_wait = 180
    start = time.time()
    job_info = None
    while time.time() - start < max_wait:
        status_res = client.get(f"/api/v1/separations/{job_id}")
        assert status_res.status_code == 200
        job_info = status_res.json()
        if job_info["status"] in ["completed", "failed"]:
            break
        time.sleep(1)

    # 4. Check separation status
    assert job_info is not None
    assert job_info["status"] == "completed"
    assert job_info["progress"] == 100
    assert len(job_info["stems"]) == 2

    stem_types = [s["stem_type"] for s in job_info["stems"]]
    assert "vocals" in stem_types
    assert "instrumental" in stem_types

    # 5. Test download individual stem
    vocals_stem = next(s for s in job_info["stems"] if s["stem_type"] == "vocals")
    stem_dl = client.get(vocals_stem["download_url"])
    assert stem_dl.status_code == 200
    assert len(stem_dl.content) > 1000

    # 6. Test download streaming ZIP archive
    zip_res = client.get(f"/api/v1/separations/{job_id}/download-zip")
    assert zip_res.status_code == 200
    assert zip_res.headers["content-type"] == "application/zip"
    
    # Verify ZIP integrity
    zip_obj = zipfile.ZipFile(io.BytesIO(zip_res.content))
    namelist = zip_obj.namelist()
    assert len(namelist) == 2
    assert any("vocals" in name for name in namelist)
    assert any("instrumental" in name for name in namelist)

    # 7. Test IDOR protection: access from different session is forbidden
    unauth_headers = {"X-Session-ID": "unauthorized_attacker_session_9999"}
    forbidden_res = client.delete(f"/api/v1/projects/{project_id}", headers=unauth_headers)
    assert forbidden_res.status_code == 403

    # 8. Test authorized project deletion
    del_res = client.delete(f"/api/v1/projects/{project_id}")
    assert del_res.status_code == 200

    # Verify project is gone
    get_res = client.get(f"/api/v1/projects/{project_id}")
    assert get_res.status_code == 404
