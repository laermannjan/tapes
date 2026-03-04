from dataclasses import dataclass
from datetime import datetime, timezone
from tapes.db.repository import Repository


@dataclass
class ImportSession:
    session_id: int
    repo: Repository

    @classmethod
    def create(cls, repo: Repository, source_path: str) -> "ImportSession":
        sid = repo.create_session(source_path)
        return cls(session_id=sid, repo=repo)

    @classmethod
    def find_in_progress(cls, repo: Repository) -> list[dict]:
        return repo.get_in_progress_sessions()

    def add_operation(self, source_path: str, op_type: str) -> int:
        return self.repo.create_operation(self.session_id, source_path, op_type)

    def update_operation(self, op_id: int, **kwargs) -> None:
        self.repo.update_operation(op_id, **kwargs)

    def complete(self) -> None:
        self.repo.update_session_state(
            self.session_id,
            "completed",
            finished_at=datetime.now(timezone.utc).isoformat(),
        )

    def abort(self) -> None:
        self.repo.update_session_state(self.session_id, "aborted")
