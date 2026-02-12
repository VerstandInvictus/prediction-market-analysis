"""Cross-platform setup script: download and extract the becker dataset.

Replaces the bash-only install-tools.sh + download.sh scripts.
Works on Windows (PowerShell), macOS, and Linux with no system tools
beyond Python -- uses httpx for download, zstandard for decompression,
and stdlib tarfile for extraction.

Usage:
    uv run scripts/setup.py
"""

from __future__ import annotations

import sys
import tarfile
import tempfile
from pathlib import Path

import httpx
import zstandard as zstd
from tqdm import tqdm

URL = "https://s3.jbecker.dev/data.tar.zst"
DATA_DIR = Path("data")


def download_and_extract() -> None:
    if DATA_DIR.exists():
        print(f"Data directory '{DATA_DIR}' already exists, skipping download.")
        return

    print(f"Downloading dataset from {URL} ...")
    print("(This is ~36 GiB compressed -- grab a coffee.)\n")

    # Stream download to a temp file so we don't hold 36GB in RAM
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".tar.zst")
    tmp_path = Path(tmp.name)

    try:
        with httpx.stream("GET", URL, follow_redirects=True, timeout=None) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0)) or None
            with tqdm(total=total, unit="B", unit_scale=True, desc="Downloading") as pbar:
                with open(tmp_path, "wb") as f:
                    for chunk in resp.iter_bytes(chunk_size=1024 * 1024):  # 1MB chunks
                        f.write(chunk)
                        pbar.update(len(chunk))

        print("\nDecompressing and extracting...")

        # Decompress zstd -> tar, then extract
        dctx = zstd.ZstdDecompressor()
        with open(tmp_path, "rb") as compressed:
            with dctx.stream_reader(compressed) as reader:
                # Wrap in a BytesIO-like seekable stream for tarfile
                # tarfile needs a file-like object; stream_reader is not seekable
                # so we use tarfile's streaming mode (r|)
                with tarfile.open(fileobj=reader, mode="r|") as tar:
                    tar.extractall()

        if not DATA_DIR.exists():
            print(f"\nWarning: Expected '{DATA_DIR}' directory was not created.")
            print("The archive may use a different top-level directory name.")
            print("Check the current directory for extracted files.")
        else:
            print(f"\nExtraction complete. Data directory: {DATA_DIR}/")

    except httpx.HTTPStatusError as e:
        print(f"\nDownload failed: HTTP {e.response.status_code}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nDownload interrupted. Run again to retry.")
        sys.exit(1)
    finally:
        # Clean up temp file
        try:
            tmp_path.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    download_and_extract()
