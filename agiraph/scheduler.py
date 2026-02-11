"""Scheduler — manages the work board and assigns nodes to workers."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Callable, Awaitable

from agiraph.models import WorkBoard, WorkNode, Worker, WorkerPool

if TYPE_CHECKING:
    from agiraph.events import EventBus

logger = logging.getLogger(__name__)


class Scheduler:
    """Assigns ready work nodes to idle workers and launches execution."""

    def __init__(
        self,
        board: WorkBoard,
        worker_pool: WorkerPool,
        executor_factory: Callable[[Worker, WorkNode], Awaitable[str]],
        event_bus: "EventBus | None" = None,
    ):
        self.board = board
        self.worker_pool = worker_pool
        self._executor_factory = executor_factory
        self._event_bus = event_bus
        self._running_tasks: dict[str, asyncio.Task] = {}

    async def tick(self):
        """Check for ready nodes and assign to idle workers."""
        ready = self.board.ready_nodes()
        idle = self.worker_pool.idle_workers()

        for node in ready:
            if not idle:
                break

            # If node has an assigned worker, use that one
            if node.assigned_worker:
                worker = self.worker_pool.get(node.assigned_worker)
                if worker and worker.status == "idle":
                    await self._launch(node, worker)
                    idle = [w for w in idle if w.id != worker.id]
                continue

            # Otherwise pick the first idle worker
            worker = idle.pop(0)
            await self._launch(node, worker)

    async def _launch(self, node: WorkNode, worker: Worker):
        """Launch a worker execution in the background."""
        node.status = "assigned"
        node.assigned_worker = worker.id
        worker.status = "busy"

        logger.info(f"Launching {worker.name} on node {node.id}: {node.task[:60]}")

        task = asyncio.create_task(self._execute_and_cleanup(node, worker))
        self._running_tasks[node.id] = task

    async def _execute_and_cleanup(self, node: WorkNode, worker: Worker):
        """Execute a node and clean up after."""
        try:
            result = await self._executor_factory(worker, node)
            if node.status not in ("completed", "failed"):
                node.status = "completed"
                node.result = result
            logger.info(f"Node {node.id} completed by {worker.name}")
        except Exception as e:
            node.status = "failed"
            node.result = f"Execution error: {e}"
            logger.error(f"Node {node.id} failed: {e}", exc_info=True)
        finally:
            if worker.status == "busy":
                worker.status = "idle"
            self._running_tasks.pop(node.id, None)
            # Trigger another tick to check for newly ready nodes
            await self.tick()

    def is_stage_complete(self, node_ids: list[str]) -> bool:
        """Check if all nodes in a stage are done (completed or failed)."""
        for nid in node_ids:
            node = self.board.get(nid)
            if node and node.status not in ("completed", "failed"):
                return False
        return True

    def active_count(self) -> int:
        return len(self._running_tasks)

    async def wait_for_nodes(self, node_ids: list[str], timeout: float = 600):
        """Wait for specific nodes to complete."""
        start = asyncio.get_event_loop().time()
        while not self.is_stage_complete(node_ids):
            if asyncio.get_event_loop().time() - start > timeout:
                logger.warning(f"Timeout waiting for nodes: {node_ids}")
                break
            await asyncio.sleep(1)
