"""output/ 전체를 Git 밖의 ZIP 으로 백업한다 (output/ 은 .gitignore 대상).

    .venv\Scripts\python.exe -m scripts.backup_outputs [대상폴더]

기본 대상: 프로젝트 옆 `shorts-ai-backups/`. 기존 ZIP 은 지우지 않고 날짜·시간을 붙여 새로 만든다.
OneDrive 안에 두면 클라우드에도 올라가므로, 용량이 부담되면 다른 드라이브를 지정한다.
"""
from __future__ import annotations

import datetime as dt
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def backup(dest: Path | None = None) -> Path:
    src = ROOT / "output"
    dest = Path(dest) if dest else ROOT.parent / "shorts-ai-backups"
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / f"output_{dt.datetime.now():%Y%m%d_%H%M%S}.zip"
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for f in sorted(src.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(ROOT))
    return out


if __name__ == "__main__":
    path = backup(Path(sys.argv[1]) if len(sys.argv) > 1 else None)
    print(f"백업 완료: {path} ({path.stat().st_size // (1024 * 1024)} MB)")
