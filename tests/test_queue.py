"""Unit tests for QueueManager and batch queue logic."""

import pytest
from poke_saifu.queue_manager import QueueItem, QueueManager, QueueStatus


def test_queue_add_and_counts():
    qm = QueueManager()
    assert qm.total_count == 0
    assert not qm.has_unprocessed

    i1 = qm.add_file("video1.mp4")
    assert qm.total_count == 1
    assert qm.waiting_count == 1
    assert qm.has_unprocessed
    assert i1.display_name == "video1.mp4"
    assert i1.status == QueueStatus.WAITING

    items = qm.add_files(["video2.mp4", "video3.mp4"])
    assert len(items) == 2
    assert qm.total_count == 3
    assert qm.waiting_count == 3


def test_queue_get_next_waiting():
    qm = QueueManager()
    i1 = qm.add_file("video1.mp4")
    i2 = qm.add_file("video2.mp4")

    next_item = qm.get_next_waiting()
    assert next_item == i1

    i1.status = QueueStatus.PROCESSING
    next_item2 = qm.get_next_waiting()
    assert next_item2 == i2

    i2.status = QueueStatus.COMPLETED
    assert qm.get_next_waiting() is None


def test_queue_remove_by_id():
    qm = QueueManager()
    i1 = qm.add_file("video1.mp4")
    i2 = qm.add_file("video2.mp4")

    assert qm.remove_by_id(i1.item_id) is True
    assert qm.total_count == 1
    assert qm.items[0].item_id == i2.item_id

    assert qm.remove_by_id("nonexistent") is False


def test_queue_move_item_reorder():
    qm = QueueManager()
    i1 = qm.add_file("video1.mp4")
    i2 = qm.add_file("video2.mp4")
    i3 = qm.add_file("video3.mp4")

    # Move video1 (index 0) to index 2
    assert qm.move_item(0, 2) is True
    assert [x.display_name for x in qm.items] == ["video2.mp4", "video3.mp4", "video1.mp4"]

    # Move video1 (index 2) to index 0
    assert qm.move_item(2, 0) is True
    assert [x.display_name for x in qm.items] == ["video1.mp4", "video2.mp4", "video3.mp4"]

    # Invalid indices
    assert qm.move_item(-1, 2) is False
    assert qm.move_item(0, 10) is False


def test_queue_clear_completed_and_all():
    qm = QueueManager()
    i1 = qm.add_file("video1.mp4")
    i2 = qm.add_file("video2.mp4")
    i3 = qm.add_file("video3.mp4")

    i1.status = QueueStatus.COMPLETED
    i2.status = QueueStatus.PROCESSING
    i3.status = QueueStatus.WAITING

    # Clear completed should remove i1 only
    removed = qm.clear_completed()
    assert removed == 1
    assert qm.total_count == 2
    assert qm.get_by_id(i1.item_id) is None
    assert qm.get_by_id(i2.item_id) is not None

    # Clear all should remove waiting items but keep currently processing item
    removed_all = qm.clear_all()
    assert removed_all == 1
    assert qm.total_count == 1
    assert qm.items[0].item_id == i2.item_id


def test_queue_status_labels():
    assert QueueStatus.WAITING.label == "待機中"
    assert QueueStatus.PROCESSING.label == "解析中"
    assert QueueStatus.COMPLETED.label == "完了 ✓"
    assert QueueStatus.ERROR.label == "エラー ⚠"
    assert QueueStatus.CANCELLED.label == "中断"


def test_queue_item_properties():
    item = QueueItem(file_path="C:/videos/2026-09-01_battle.mp4")
    assert item.display_name == "2026-09-01_battle.mp4"
    assert len(item.item_id) == 8
    assert item.status == QueueStatus.WAITING
