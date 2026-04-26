#!/usr/bin/env python3
"""
Upload APK (or any file) to Yandex Disk via REST API:
1) upload file
2) publish by link
3) return public_url and direct download link

Security note:
- Keep secrets in environment variables, do not commit real token values to git.
"""

from __future__ import annotations

import datetime as dt
import http.client
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Optional


# ==========================
# CONFIG CONSTANTS
# ==========================
# Use placeholders here and provide real values via environment variables.
YANDEX_OAUTH_TOKEN = os.getenv("YANDEX_OAUTH_TOKEN", "PASTE_YANDEX_OAUTH_TOKEN_HERE")
APK_DIR = os.getenv("APK_DIR", r"G:\path\to\your\project\build\app\outputs\flutter-apk")
DISK_UPLOAD_DIR = os.getenv("DISK_UPLOAD_DIR", "disk:/apk_builds")
OVERWRITE_IF_EXISTS = os.getenv("OVERWRITE_IF_EXISTS", "true").lower() == "true"
APK_GLOB_PATTERN = os.getenv("APK_GLOB_PATTERN", "*.apk")
APK_SEARCH_RECURSIVE = os.getenv("APK_SEARCH_RECURSIVE", "false").lower() == "true"


API_BASE = "https://cloud-api.yandex.net/v1/disk"
TIMEOUT_SECONDS = 120


def fail(message: str) -> None:
    raise RuntimeError(message)


def api_request(
    method: str,
    endpoint: str,
    token: str,
    *,
    params: Optional[dict[str, Any]] = None,
    json_body: Optional[dict[str, Any]] = None,
    expected_statuses: tuple[int, ...] = (200,),
    use_auth: bool = True,
) -> dict[str, Any]:
    url = f"{API_BASE}{endpoint}"
    if params:
        url += "?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)

    headers: dict[str, str] = {"Accept": "application/json"}
    payload: Optional[bytes] = None

    if use_auth:
        headers["Authorization"] = f"OAuth {token}"

    if json_body is not None:
        payload = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"

    request = urllib.request.Request(url=url, data=payload, headers=headers, method=method)

    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            status = response.status
            body = response.read()
            content_type = response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as http_error:
        error_body = http_error.read().decode("utf-8", errors="replace")
        fail(
            f"HTTP {http_error.code} for {method} {url}\n"
            f"Response: {error_body}"
        )

    if status not in expected_statuses:
        fail(
            f"Unexpected status {status} for {method} {url}. "
            f"Expected one of {expected_statuses}."
        )

    if not body:
        return {}

    if "application/json" in content_type:
        return json.loads(body.decode("utf-8"))

    return {"raw_body": body.decode("utf-8", errors="replace")}


def ensure_remote_directory(token: str, remote_dir: str) -> None:
    try:
        meta = api_request(
            "GET",
            "/resources",
            token,
            params={"path": remote_dir, "fields": "path,type"},
            expected_statuses=(200,),
        )
        if meta.get("type") != "dir":
            fail(f"Path {remote_dir} exists, but it is not a folder.")
        return
    except RuntimeError as error:
        if "HTTP 404" not in str(error):
            raise

    api_request(
        "PUT",
        "/resources",
        token,
        params={"path": remote_dir},
        expected_statuses=(201,),
    )


def ensure_remote_directory_tree(token: str, remote_dir: str) -> None:
    """Create nested remote folders if they do not exist."""
    root = None
    if remote_dir.startswith("disk:/"):
        root = "disk:/"
    elif remote_dir.startswith("app:/"):
        root = "app:/"
    else:
        fail("DISK_UPLOAD_DIR must start with disk:/ or app:/")

    suffix = remote_dir[len(root):].strip("/")
    if not suffix:
        return

    current = root.rstrip("/")
    for part in suffix.split("/"):
        current = f"{current}/{part}"
        ensure_remote_directory(token, current)


def upload_binary_to_href(upload_href: str, local_file: Path) -> int:
    parsed = urllib.parse.urlparse(upload_href)
    if parsed.scheme not in {"http", "https"}:
        fail(f"Invalid upload URL: {upload_href}")

    connection_cls = (
        http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    )
    path_with_query = parsed.path + (f"?{parsed.query}" if parsed.query else "")
    content_type = mimetypes.guess_type(local_file.name)[0] or "application/octet-stream"

    connection = connection_cls(parsed.netloc, timeout=TIMEOUT_SECONDS)
    try:
        connection.putrequest("PUT", path_with_query)
        connection.putheader("Content-Type", content_type)
        connection.putheader("Content-Length", str(local_file.stat().st_size))
        connection.endheaders()

        with local_file.open("rb") as file_stream:
            while True:
                chunk = file_stream.read(1024 * 1024)
                if not chunk:
                    break
                connection.send(chunk)

        response = connection.getresponse()
        status = response.status
        response_body = response.read().decode("utf-8", errors="replace")
    finally:
        connection.close()

    if status not in (201, 202):
        fail(f"File upload failed: HTTP {status}. Response: {response_body}")

    return status


def find_latest_apk(apk_dir: Path) -> Path:
    """Find the most recent APK file in the directory by modification time."""
    if not apk_dir.exists() or not apk_dir.is_dir():
        fail(f"APK directory not found: {apk_dir}")

    if APK_SEARCH_RECURSIVE:
        apk_files = list(apk_dir.rglob(APK_GLOB_PATTERN))
    else:
        apk_files = list(apk_dir.glob(APK_GLOB_PATTERN))

    apk_files = [file for file in apk_files if file.is_file()]
    if not apk_files:
        fail(
            "No APK files found in "
            f"{apk_dir} with pattern '{APK_GLOB_PATTERN}' (recursive={APK_SEARCH_RECURSIVE})."
        )

    latest = max(apk_files, key=lambda f: f.stat().st_mtime)
    modified_at = dt.datetime.fromtimestamp(latest.stat().st_mtime).isoformat(timespec="seconds")
    print(
        f"Found latest APK: {latest.name} (modified: {modified_at})",
        file=sys.stderr,
    )
    return latest


def main() -> int:
    token = YANDEX_OAUTH_TOKEN.strip()
    if not token or token == "PASTE_YANDEX_OAUTH_TOKEN_HERE":
        fail("Set YANDEX_OAUTH_TOKEN via env var or in script constants.")

    apk_dir = Path(APK_DIR).expanduser().resolve()
    local_file = find_latest_apk(apk_dir)

    remote_dir = DISK_UPLOAD_DIR.strip().rstrip("/")
    if not remote_dir.startswith(("disk:/", "app:/")):
        fail("DISK_UPLOAD_DIR must start with disk:/ or app:/")

    remote_path = f"{remote_dir}/{local_file.name}"

    ensure_remote_directory_tree(token, remote_dir)

    upload_link = api_request(
        "GET",
        "/resources/upload",
        token,
        params={
            "path": remote_path,
            "overwrite": str(OVERWRITE_IF_EXISTS).lower(),
        },
        expected_statuses=(200,),
    )

    upload_href = upload_link.get("href")
    if not upload_href:
        fail("API did not return upload href.")

    upload_status = upload_binary_to_href(upload_href, local_file)

    api_request(
        "PUT",
        "/resources/publish",
        token,
        params={"path": remote_path},
        expected_statuses=(200,),
    )

    file_meta = api_request(
        "GET",
        "/resources",
        token,
        params={
            "path": remote_path,
            "fields": "name,path,size,file,public_url,public_key",
        },
        expected_statuses=(200,),
    )

    public_key = file_meta.get("public_key")
    public_url = file_meta.get("public_url")
    if not public_key or not public_url:
        fail("Could not get public_key/public_url after publish.")

    direct_download = api_request(
        "GET",
        "/public/resources/download",
        token,
        params={"public_key": public_key},
        expected_statuses=(200,),
    )

    result = {
        "uploaded_local_file": str(local_file),
        "remote_path": remote_path,
        "upload_status": upload_status,
        "public_url": public_url,
        "direct_download_url": direct_download.get("href"),
        "note": "public_url is the stable public page; direct_download_url is usually temporary.",
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
