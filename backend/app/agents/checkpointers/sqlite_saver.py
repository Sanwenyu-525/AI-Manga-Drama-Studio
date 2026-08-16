"""SQLite Checkpointer — custom BaseCheckpointSaver on stdlib sqlite3 (P7-T004).

The LangGraph Director is compiled with this checkpointer so the graph execution
state (channel values, versions, pending writes) persists per run. Checkpoint
records are keyed by thread_id = run_id, so a run can be resumed after restart.
The business AgentRun row lives in the SQLAlchemy agent_runs table; this saver
stores ONLY the LangGraph thread state (red line: Checkpoint ≠ Project DB).

Uses the standard-library sqlite3 module (no new dependency). Only a minimal
subset of the BaseCheckpointSaver surface is needed for the linear Director graph.

Thread safety: sqlite3 connections are not safe to share across threads; every
public operation is serialized behind a reentrant lock (multiple run graph tasks
can execute concurrently on one store).
"""

from __future__ import annotations

import asyncio
import sqlite3
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    CheckpointTuple,
    PendingWrite,
)
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.types import RunnableConfig

_MAKE_TABLES = """
CREATE TABLE IF NOT EXISTS checkpoints (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    parent_checkpoint_id TEXT,
    type TEXT,
    checkpoint BLOB NOT NULL,
    metadata BLOB,
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);
CREATE TABLE IF NOT EXISTS checkpoint_writes (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    idx INTEGER NOT NULL,
    channel TEXT NOT NULL,
    type TEXT,
    blob BLOB NOT NULL,
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
);
CREATE INDEX IF NOT EXISTS idx_cpw_thread_checkpoint
    ON checkpoint_writes (thread_id, checkpoint_ns, checkpoint_id);
"""


@dataclass
class SqliteCheckpointSaver(BaseCheckpointSaver):
    """A BaseCheckpointSaver backed by stdlib sqlite3 (P7-T004).
    One sqlite file holds all threads; each run maps to thread_id = run_id.
    WAL mode is enabled for crash safety. In-memory when no path given (tests).
    """

    conn: sqlite3.Connection = field(init=False)
    load_memory: bool = False
    _lock: threading.RLock = field(default_factory=threading.RLock)

    def __init__(self, checkpoint_path: str | Path | None = None) -> None:
        super().__init__(serde=JsonPlusSerializer())
        self._lock = threading.RLock()  # custom __init__ skips the dataclass init
        path = Path(checkpoint_path) if checkpoint_path else None
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
        target = ":memory:" if path is None else str(path)
        self.conn = sqlite3.connect(target, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_MAKE_TABLES)
        try:
            self.conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.DatabaseError:
            pass
        self.conn.commit()

    def close(self) -> None:
        with self._lock:
            try:
                self.conn.close()
            except sqlite3.Error:
                pass

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        with self._lock:
            thread_id = _thread_id(config)
            checkpoint_ns = _checkpoint_ns(config)
            checkpoint_id = _config_checkpoint_id(config)
            if not checkpoint_id:
                row = self.conn.execute(
                    "SELECT checkpoint_id FROM checkpoints WHERE thread_id=? AND checkpoint_ns=? "
                    "ORDER BY checkpoint_id DESC LIMIT 1",
                    (thread_id, checkpoint_ns),
                ).fetchone()
                if row:
                    checkpoint_id = row["checkpoint_id"]
            if not checkpoint_id:
                return None
            row = self.conn.execute(
                "SELECT type, checkpoint, metadata, parent_checkpoint_id FROM checkpoints "
                "WHERE thread_id=? AND checkpoint_ns=? AND checkpoint_id=?",
                (thread_id, checkpoint_ns, checkpoint_id),
            ).fetchone()
            if row is None:
                return None
            checkpoint = self.serde.loads_typed((row["type"], row["checkpoint"]))
            metadata = self.serde.loads_typed((row["type"], row["metadata"])) if row["metadata"] else {"source": "loop", "step": 0, "parents": {}}
            parent_config = None
            if row["parent_checkpoint_id"]:
                parent_config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": checkpoint_ns, "checkpoint_id": row["parent_checkpoint_id"]}}
            pending = self._pending_writes(thread_id, checkpoint_ns, checkpoint_id)
            return CheckpointTuple(
                config={"configurable": {"thread_id": thread_id, "checkpoint_ns": checkpoint_ns, "checkpoint_id": checkpoint_id}},
                checkpoint=checkpoint,
                metadata=metadata,
                parent_config=parent_config,
                pending_writes=pending,
            )

    def put(self, config, checkpoint, metadata, new_versions):
        with self._lock:
            thread_id = _thread_id(config)
            checkpoint_ns = _checkpoint_ns(config)
            checkpoint_id = checkpoint.get("id")
            type_, blob = self.serde.dumps_typed(checkpoint)
            _meta_type, meta_blob = self.serde.dumps_typed(metadata)
            parent_cid = _config_checkpoint_id(config)
            self.conn.execute(
                "INSERT OR REPLACE INTO checkpoints "
                "(thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, type, checkpoint, metadata) "
                "VALUES (?,?,?,?,?,?,?)",
                (thread_id, checkpoint_ns, checkpoint_id, parent_cid, type_, blob, meta_blob),
            )
            self.conn.commit()
            return {"configurable": {"thread_id": thread_id, "checkpoint_ns": checkpoint_ns, "checkpoint_id": checkpoint_id}}

    def put_writes(self, config, writes, task_id: str, task_path: str = "") -> None:
        with self._lock:
            thread_id = _thread_id(config)
            checkpoint_ns = _checkpoint_ns(config)
            checkpoint_id = _config_checkpoint_id(config)
            for idx, write in enumerate(writes):
                channel = write[0]
                if len(write) == 3:
                    payload = (write[1], write[2])
                else:
                    payload = write[1]
                type_, blob = self.serde.dumps_typed(payload)
                self.conn.execute(
                    "INSERT OR REPLACE INTO checkpoint_writes "
                    "(thread_id, checkpoint_ns, checkpoint_id, task_id, idx, channel, type, blob) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (thread_id, checkpoint_ns, checkpoint_id, task_id, idx, channel, type_, blob),
                )
            self.conn.commit()

    def list(self, config, *, filter=None, before=None, limit=None):
        with self._lock:
            thread_id = _thread_id(config)
            checkpoint_ns = _checkpoint_ns(config)
            args: list[Any] = [thread_id, checkpoint_ns]
            sql = "SELECT checkpoint_id, type, checkpoint, metadata, parent_checkpoint_id "
            sql += "FROM checkpoints WHERE thread_id=? AND checkpoint_ns=?"
            if before:
                sql += " AND checkpoint_id < ?"
                args.append(before["configurable"]["checkpoint_id"])
            sql += " ORDER BY checkpoint_id DESC"
            if limit:
                sql += " LIMIT ?"
                args.append(limit)
            rows = self.conn.execute(sql, args).fetchall()
        for row in rows:
            config_out = {"configurable": {"thread_id": thread_id, "checkpoint_ns": checkpoint_ns, "checkpoint_id": row["checkpoint_id"]}}
            parent_config = None
            if row["parent_checkpoint_id"]:
                parent_config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": checkpoint_ns, "checkpoint_id": row["parent_checkpoint_id"]}}
            pending = self._pending_writes(thread_id, checkpoint_ns, row["checkpoint_id"])
            yield CheckpointTuple(
                config=config_out,
                checkpoint=self.serde.loads_typed((row["type"], row["checkpoint"])),
                metadata=self.serde.loads_typed((row["type"], row["metadata"])) if row["metadata"] else {},
                parent_config=parent_config,
                pending_writes=pending,
            )

    def get_next_version(self, current: str | None, channel: str) -> str:
        current_v = 0
        if current is not None:
            try:
                current_v = int(current)
            except ValueError:
                current_v = 0
        return str(current_v + 1)

    # ---------- async contract (LangGraph ainvoke uses these) ----------

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        return await asyncio.to_thread(self.get_tuple, config)

    async def aput(self, config, checkpoint, metadata, new_versions) -> RunnableConfig:
        return await asyncio.to_thread(self.put, config, checkpoint, metadata, new_versions)

    async def aput_writes(self, config, writes, task_id: str, task_path: str = "") -> None:
        await asyncio.to_thread(self.put_writes, config, writes, task_id, task_path)

    async def alist(self, config, *, filter=None, before=None, limit=None):
        items = await asyncio.to_thread(list, self.list(config, filter=filter, before=before, limit=limit))
        for item in items:
            yield item

    async def aget(self, config):
        return await self.aget_tuple(config)

    async def adelete_thread(self, thread_id: str) -> None:
        await asyncio.to_thread(self.delete_thread, thread_id)

    def delete_thread(self, thread_id: str) -> None:
        with self._lock:
            self.conn.execute("DELETE FROM checkpoint_writes WHERE thread_id=?", (thread_id,))
            self.conn.execute("DELETE FROM checkpoints WHERE thread_id=?", (thread_id,))
            self.conn.commit()

    def _pending_writes(self, thread_id: str, checkpoint_ns: str, checkpoint_id: str) -> list[PendingWrite] | None:
        rows = self.conn.execute(
            "SELECT task_id, channel, type, blob FROM checkpoint_writes "
            "WHERE thread_id=? AND checkpoint_ns=? AND checkpoint_id=? ORDER BY idx",
            (thread_id, checkpoint_ns, checkpoint_id or ""),
        ).fetchall()
        if not rows:
            return None
        writes: list[tuple] = []
        for r in rows:
            value = self.serde.loads_typed((r["type"], r["blob"]))
            # langgraph expects PendingWrite = (task_id, channel, value)
            writes.append((r["task_id"], r["channel"], value))
        return writes


def _thread_id(config: RunnableConfig) -> str:
    return str((config.get("configurable") or {}).get("thread_id") or "")


def _checkpoint_ns(config: RunnableConfig) -> str:
    return str((config.get("configurable") or {}).get("checkpoint_ns") or "")


def _config_checkpoint_id(config: RunnableConfig) -> str | None:
    return (config.get("configurable") or {}).get("checkpoint_id")
