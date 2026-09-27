# -*- coding: utf-8 -*-

"""
sync_and_unzip.py

Đọc danh sách ZIP từ drive_zips.json.

Flow:

1. Load drive_zips.json
2. Load zip_progress.json
3. Với từng ZIP:
   - Nếu đã extract thành công -> skip
   - Nếu chưa:
       + gdown ZIP
       + verify ZIP
       + unzip JPG
       + update progress
       + xóa ZIP local để tiết kiệm disk

Resumable:
- Có thể Ctrl+C giữa chừng.
- ZIP chưa hoàn thành sẽ được xử lý lại ở lần chạy sau.
- ZIP đã hoàn thành sẽ không gdown lại.
"""

import argparse
import json
import os
import zipfile
from pathlib import Path

import gdown


# ============================================================
# JSON
# ============================================================

def load_json(path: Path, default):
    if not path.exists():
        return default

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    except (json.JSONDecodeError, OSError) as e:
        print(f"[WARN] Không đọc được {path}: {e}")
        return default


def save_json(path: Path, data):
    """
    Atomic write:
    ghi vào .tmp trước rồi replace.
    """

    tmp = path.with_suffix(path.suffix + ".tmp")

    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2,
        )

    tmp.replace(path)


# ============================================================
# ZIP VALIDATION
# ============================================================

def is_valid_zip(path: Path) -> bool:
    if not path.exists():
        return False

    if path.stat().st_size == 0:
        return False

    try:
        with zipfile.ZipFile(path, "r") as zf:
            return zf.testzip() is None

    except (zipfile.BadZipFile, OSError):
        return False


# ============================================================
# DOWNLOAD
# ============================================================

def download_zip(
    file_id: str,
    name: str,
    zip_dir: Path,
) -> Path:

    zip_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    output = zip_dir / name

    # --------------------------------------------------------
    # ZIP local tồn tại
    # --------------------------------------------------------

    if output.exists():

        if is_valid_zip(output):
            print("  [FOUND] ZIP local đã tồn tại.")
            return output

        print(
            "  [WARN] ZIP local bị hỏng."
        )

        try:
            output.unlink()
        except OSError:
            pass

    # --------------------------------------------------------
    # Download
    # --------------------------------------------------------

    print()
    print("  [GDOWN] Downloading...")
    print(f"  ID: {file_id}")
    print(f"  -> {output}")

    result = gdown.download(
        id=file_id,
        output=str(output),
        quiet=False,
        fuzzy=False,
    )

    if result is None:
        raise RuntimeError(
            "gdown download failed."
        )

    # --------------------------------------------------------
    # Verify
    # --------------------------------------------------------

    print("  [VERIFY] Checking ZIP...")

    if not is_valid_zip(output):
        raise RuntimeError(
            f"Downloaded file is not a valid ZIP: {output}"
        )

    print("  [OK] ZIP valid.")

    return output


# ============================================================
# UNZIP
# ============================================================

def unzip_zip(
    zip_path: Path,
    out_dir: Path,
    existing: set[str],
):
    """
    Extract tất cả JPG vào out_dir theo dạng flat.

    Return:
        extracted_count
        skipped_count
    """

    extracted_count = 0
    skipped_count = 0

    out_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    with zipfile.ZipFile(zip_path, "r") as zf:

        members = [
            m
            for m in zf.namelist()
            if (
                not m.endswith("/")
                and os.path.basename(m).lower().endswith(".jpg")
            )
        ]

        total = len(members)

        print(
            f"  [UNZIP] {total} JPG"
        )

        for index, member in enumerate(
            members,
            1,
        ):

            fname = os.path.basename(member)

            # ------------------------------------------------
            # Already exists
            # ------------------------------------------------

            if fname in existing:
                skipped_count += 1
                continue

            output = out_dir / fname

            # ------------------------------------------------
            # Extract
            # ------------------------------------------------

            with zf.open(member) as src:
                with open(output, "wb") as dst:

                    while True:
                        chunk = src.read(
                            1024 * 1024
                        )

                        if not chunk:
                            break

                        dst.write(chunk)

            existing.add(fname)

            extracted_count += 1

            # Progress mỗi 100 file
            if (
                index % 100 == 0
                or index == total
            ):
                print(
                    f"    {index}/{total}"
                )

    return (
        extracted_count,
        skipped_count,
    )


# ============================================================
# MAIN
# ============================================================

def sync(
    drive_json_path: Path,
    progress_path: Path,
    zip_dir: Path,
    out_dir: Path,
):
    # --------------------------------------------------------
    # Load Drive JSON
    # --------------------------------------------------------

    drive_data = load_json(
        drive_json_path,
        default={
            "files": []
        },
    )

    drive_files = drive_data.get(
        "files",
        [],
    )

    if not drive_files:
        print(
            "[ERROR] drive_zips.json không có ZIP."
        )
        return

    # --------------------------------------------------------
    # Load local progress
    # --------------------------------------------------------

    progress = load_json(
        progress_path,
        default={
            "files": {}
        },
    )

    progress.setdefault(
        "files",
        {},
    )

    # --------------------------------------------------------
    # Existing images
    # --------------------------------------------------------

    out_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    existing = {
        p.name
        for p in out_dir.glob("*.jpg")
    }

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("AIC2026 ZIP SYNC")
    print("=" * 70)

    print(
        f"Drive JSON : {drive_json_path}"
    )

    print(
        f"ZIP dir    : {zip_dir}"
    )

    print(
        f"Images dir : {out_dir}"
    )

    print(
        f"Drive ZIPs : {len(drive_files)}"
    )

    print(
        f"Existing JPG: {len(existing)}"
    )

    print("=" * 70)

    total = len(drive_files)

    downloaded = 0
    skipped = 0
    extracted = 0
    failed = 0
    deleted = 0

    # ========================================================
    # PROCESS
    # ========================================================

    for index, item in enumerate(
        drive_files,
        1,
    ):

        file_id = item["id"]
        name = item["name"]

        print()
        print(
            f"[{index}/{total}] {name}"
        )

        # ----------------------------------------------------
        # Check progress
        # ----------------------------------------------------

        state = progress["files"].get(
            file_id,
            {}
        )

        if state.get("status") == "extracted":

            print(
                "  [SKIP] Đã extract trước đó."
            )

            skipped += 1
            continue

        # ----------------------------------------------------
        # Download
        # ----------------------------------------------------

        try:

            zip_path = download_zip(
                file_id=file_id,
                name=name,
                zip_dir=zip_dir,
            )

            downloaded += 1

        except Exception as e:

            print(
                f"  [ERROR] Download: {e}"
            )

            progress["files"][file_id] = {
                "name": name,
                "status": "download_failed",
                "error": str(e),
            }

            save_json(
                progress_path,
                progress,
            )

            failed += 1
            continue

        # ----------------------------------------------------
        # Unzip
        # ----------------------------------------------------

        try:

            new_count, skip_count = unzip_zip(
                zip_path=zip_path,
                out_dir=out_dir,
                existing=existing,
            )

            extracted += new_count

            # ------------------------------------------------
            # IMPORTANT:
            # Chỉ mark extracted SAU KHI unzip thành công.
            # ------------------------------------------------

            progress["files"][file_id] = {
                "name": name,
                "status": "extracted",
                "jpg_extracted": new_count,
                "jpg_skipped": skip_count,
            }

            save_json(
                progress_path,
                progress,
            )

            print()
            print(
                f"  [OK] Extracted: {new_count}"
            )

            print(
                f"  [SKIP] Existing JPG: {skip_count}"
            )

            # ------------------------------------------------
            # Delete ZIP
            # ------------------------------------------------

            try:

                zip_path.unlink()

                deleted += 1

                print(
                    "  [DELETE] ZIP removed."
                )

            except OSError as e:

                print(
                    f"  [WARN] Không xóa được ZIP: {e}"
                )

        except zipfile.BadZipFile:

            print(
                "  [ERROR] ZIP corrupted."
            )

            progress["files"][file_id] = {
                "name": name,
                "status": "unzip_failed",
                "error": "BadZipFile",
            }

            save_json(
                progress_path,
                progress,
            )

            failed += 1

        except Exception as e:

            print(
                f"  [ERROR] Unzip: {e}"
            )

            progress["files"][file_id] = {
                "name": name,
                "status": "unzip_failed",
                "error": str(e),
            }

            save_json(
                progress_path,
                progress,
            )

            failed += 1

    # ========================================================
    # SUMMARY
    # ========================================================

    print()
    print("=" * 70)
    print("DONE")
    print("=" * 70)

    print(
        f"Drive ZIPs       : {total}"
    )

    print(
        f"Download/Found   : {downloaded}"
    )

    print(
        f"Already processed: {skipped}"
    )

    print(
        f"New JPG          : {extracted}"
    )

    print(
        f"ZIP deleted      : {deleted}"
    )

    print(
        f"Failed           : {failed}"
    )

    print(
        f"Total JPG        : {len(existing)}"
    )

    print("=" * 70)


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--drive-json",
        required=True,
        help="JSON export từ Google Colab",
    )

    parser.add_argument(
        "--progress",
        default="zip_progress.json",
        help="Local progress JSON",
    )

    parser.add_argument(
        "--zip-dir",
        required=True,
        help="Thư mục tạm chứa ZIP",
    )

    parser.add_argument(
        "--out",
        required=True,
        help="Thư mục static/images",
    )

    args = parser.parse_args()

    sync(
        drive_json_path=Path(
            args.drive_json
        ),
        progress_path=Path(
            args.progress
        ),
        zip_dir=Path(
            args.zip_dir
        ),
        out_dir=Path(
            args.out
        ),
    )