"""Queue management for batch processing battle recordings in Poke-Saifu."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import time
from typing import Any, Dict, List, Optional
import uuid


class QueueStatus(str, Enum):
    WAITING = "waiting"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ERROR = "error"
    CANCELLED = "cancelled"

    @property
    def label(self) -> str:
        labels = {
            QueueStatus.WAITING: "待機中",
            QueueStatus.PROCESSING: "解析中",
            QueueStatus.COMPLETED: "完了 ✓",
            QueueStatus.ERROR: "エラー ⚠",
            QueueStatus.CANCELLED: "中断",
        }
        return labels.get(self, self.value)


@dataclass
class QueueItem:
    file_path: str
    item_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    status: QueueStatus = QueueStatus.WAITING
    progress: float = 0.0
    status_text: str = ""
    json_result: str = ""
    default_filename: str = ""
    battle_data: Optional[Dict[str, Any]] = None
    preview_frame: Optional[Any] = None
    error_message: str = ""
    added_at: float = field(default_factory=time.time)

    @property
    def display_name(self) -> str:
        return Path(self.file_path).name


class QueueManager:
    """Manages the lifecycle and ordering of battle video queue items."""

    def __init__(self):
        self._items: List[QueueItem] = []

    @property
    def items(self) -> List[QueueItem]:
        return list(self._items)

    @property
    def total_count(self) -> int:
        return len(self._items)

    @property
    def waiting_count(self) -> int:
        return sum(1 for item in self._items if item.status == QueueStatus.WAITING)

    @property
    def completed_count(self) -> int:
        return sum(1 for item in self._items if item.status == QueueStatus.COMPLETED)

    @property
    def has_unprocessed(self) -> bool:
        return any(
            item.status in (QueueStatus.WAITING, QueueStatus.PROCESSING)
            for item in self._items
        )

    def add_file(self, file_path: str) -> QueueItem:
        """Add a single file to the queue."""
        item = QueueItem(file_path=file_path)
        self._items.append(item)
        return item

    def add_files(self, file_paths: List[str]) -> List[QueueItem]:
        """Add multiple files to the queue."""
        added = []
        for fp in file_paths:
            added.append(self.add_file(fp))
        return added

    def get_by_id(self, item_id: str) -> Optional[QueueItem]:
        for item in self._items:
            if item.item_id == item_id:
                return item
        return None

    def get_next_waiting(self) -> Optional[QueueItem]:
        for item in self._items:
            if item.status == QueueStatus.WAITING:
                return item
        return None

    def remove_by_id(self, item_id: str) -> bool:
        """Remove a specific item by ID."""
        for i, item in enumerate(self._items):
            if item.item_id == item_id:
                self._items.pop(i)
                return True
        return False

    def clear_completed(self) -> int:
        """Remove all completed, error, or cancelled items."""
        initial_len = len(self._items)
        self._items = [
            item
            for item in self._items
            if item.status in (QueueStatus.WAITING, QueueStatus.PROCESSING)
        ]
        return initial_len - len(self._items)

    def clear_all(self) -> int:
        """Remove all items except currently processing item."""
        initial_len = len(self._items)
        self._items = [
            item
            for item in self._items
            if item.status == QueueStatus.PROCESSING
        ]
        return initial_len - len(self._items)

    def move_item(self, from_idx: int, to_idx: int) -> bool:
        """Reorder queue item from one index to another (drag and drop)."""
        if 0 <= from_idx < len(self._items) and 0 <= to_idx < len(self._items):
            item = self._items.pop(from_idx)
            self._items.insert(to_idx, item)
            return True
        return False
