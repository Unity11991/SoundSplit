# Security & Privacy Policy — StemLab AI

StemLab AI treats all uploaded media and audio assets as untrusted, private user content.

## 1. Data Privacy & Audio Retention Policy
- **No Training on User Media**: Uploaded audio files are strictly used for requested inference and are never used to train or fine-tune models.
- **Automatic Expiration**: Audio inputs, generated stem files, and temporary processing buffers are purged automatically after a configurable retention window (default: 24 hours).
- **Manual Deletion**: Users can permanently delete their projects and all associated audio stems at any time via the Project dashboard or the `DELETE /api/v1/projects/{project_id}` API.

## 2. Media Validation & Processing Hardening
- **Strict Media Inspection**: Uploaded files are inspected using both file magic byte verification and container probing via `ffprobe`. Arbitrary executables, scripts, or malicious polyglot files are rejected before touching disk.
- **Resource Constraints**:
  - Max upload size: 100 MB.
  - Max audio duration: 600 seconds (10 minutes).
  - CPU worker thread limits and GPU memory bounds prevent denial-of-service (DoS) via resource exhaustion.
- **Path Traversal Protection**: Internal file storage keys use cryptographically random UUIDs (`uuid4().hex`). All storage resolution enforces strict path sandboxing within the configured storage directory.

## 3. Access Control & IDOR Prevention
- **Cryptographic Session Tokens**: Anonymous sessions are protected using unguessable 192-bit cryptographic tokens.
- **Insecure Direct Object Reference (IDOR) Mitigation**: Every API access to a project, separation run, stem stream, or download verifies cryptographic session ownership.
- **Signed Download URLs**: Individual stem downloads and ZIP exports use short-lived HMAC-SHA256 signed tokens to prevent unauthorized asset crawling.

## 4. Reporting Security Vulnerabilities
If you discover a security vulnerability in StemLab AI, please report it privately to `security@stemlab.ai`. We appreciate responsible disclosure and respond promptly.
