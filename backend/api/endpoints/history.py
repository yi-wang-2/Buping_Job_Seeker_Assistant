"""History API endpoints."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter

router = APIRouter()

OUTPUT_FOLDER = Path("data_folder/output")


@router.get("")
def list_history() -> dict:
    """List all generated PDF files."""
    files = []
    if OUTPUT_FOLDER.exists():
        for f in OUTPUT_FOLDER.glob("*.pdf"):
            files.append({
                "name": f.name,
                "path": str(f),
                "size": f.stat().st_size,
                "modified": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            })
    files.sort(key=lambda x: x["modified"], reverse=True)
    return {"files": files, "count": len(files)}


@router.delete("")
def clear_history() -> dict:
    """Clear all PDF files in output folder."""
    count = 0
    if OUTPUT_FOLDER.exists():
        for f in OUTPUT_FOLDER.glob("*.pdf"):
            f.unlink()
            count += 1
    return {"status": "success", "message": f"已清空 {count} 个文件", "cleared": count}
