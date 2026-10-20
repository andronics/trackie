"""Persist each tracker's last good snapshot section across restarts."""

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


class StateStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def _path(self, tracker: str) -> Path:
        return self.directory / f"{tracker}.json"

    def save(self, tracker: str, section: dict[str, Any]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        # Write then rename, so a crash never leaves a half-written file
        fd, tmp = tempfile.mkstemp(dir=self.directory, prefix=f".{tracker}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(section, f)
            os.replace(tmp, self._path(tracker))
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def load(self, tracker: str) -> dict[str, Any] | None:
        path = self._path(tracker)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as e:
            log.warning("ignoring unreadable state file %s: %s", path, e)
            return None
        return data if isinstance(data, dict) else None
