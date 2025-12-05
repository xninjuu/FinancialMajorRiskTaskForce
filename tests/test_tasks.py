from datetime import datetime, timedelta
from pathlib import Path

from app.domain import Task, TaskStatus
from app.persistence import PersistenceLayer


def test_task_roundtrip(tmp_path: Path) -> None:
    db_path = tmp_path / "tasks.db"
    persistence = PersistenceLayer(str(db_path))
    task = Task(
        id="t1",
        title="Review case",
        description="Check alerts",
        created_by="alice",
        assignee="bob",
        priority="High",
        status=TaskStatus.OPEN,
        related_case_id="case-123",
        due_at=datetime.utcnow() + timedelta(days=1),
    )
    persistence.upsert_task(task)
    items = persistence.list_tasks(assignee="bob")
    assert len(items) == 1
    assert items[0].title == task.title
    persistence.update_task_status("t1", TaskStatus.DONE)
    updated = persistence.list_tasks(assignee="bob")[0]
    assert updated.status == TaskStatus.DONE
