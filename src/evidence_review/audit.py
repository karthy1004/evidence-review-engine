"""Append-only, hash-chained audit log.

Each entry stores the SHA-256 of the previous entry, so editing, deleting or reordering
any past entry breaks `verify()`. This is tamper-*evident*, not tamper-proof: someone
who can rewrite the whole file can rebuild the chain. Anchoring the head hash
somewhere external (a signed release, a ticket, an email) closes that gap.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

GENESIS = "0" * 64


class AuditEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    seq: int
    at: datetime
    actor: str
    action: str
    detail: dict[str, Any]
    prev_hash: str
    hash: str


def _digest(
    seq: int, at: datetime, actor: str, action: str, detail: dict[str, Any], prev: str
) -> str:
    body = json.dumps(
        {
            "seq": seq,
            "at": at.isoformat(),
            "actor": actor,
            "action": action,
            "detail": detail,
            "prev": prev,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(body.encode()).hexdigest()


class AuditLog:
    def __init__(self, entries: list[AuditEntry] | None = None) -> None:
        self._entries: list[AuditEntry] = list(entries or [])

    @property
    def entries(self) -> tuple[AuditEntry, ...]:
        return tuple(self._entries)

    @property
    def head(self) -> str:
        return self._entries[-1].hash if self._entries else GENESIS

    def append(
        self,
        actor: str,
        action: str,
        detail: dict[str, Any] | None = None,
        at: datetime | None = None,
    ) -> AuditEntry:
        seq = len(self._entries)
        when = at or datetime.now(UTC)
        payload = dict(detail or {})
        entry = AuditEntry(
            seq=seq,
            at=when,
            actor=actor,
            action=action,
            detail=payload,
            prev_hash=self.head,
            hash=_digest(seq, when, actor, action, payload, self.head),
        )
        self._entries.append(entry)
        return entry

    def verify(self) -> list[str]:
        """Return a list of integrity problems; empty means the chain is intact."""
        problems: list[str] = []
        prev = GENESIS
        for i, e in enumerate(self._entries):
            if e.seq != i:
                problems.append(f"entry {i}: sequence number {e.seq}")
            if e.prev_hash != prev:
                problems.append(f"entry {i}: prev_hash does not match previous entry")
            if e.hash != _digest(e.seq, e.at, e.actor, e.action, e.detail, e.prev_hash):
                problems.append(f"entry {i}: content does not match its hash")
            prev = e.hash
        return problems

    def to_jsonl(self) -> str:
        return "".join(e.model_dump_json() + "\n" for e in self._entries)

    @classmethod
    def from_jsonl(cls, text: str) -> AuditLog:
        return cls([AuditEntry.model_validate_json(line) for line in text.splitlines() if line])
