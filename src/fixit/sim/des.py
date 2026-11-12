"""A small discrete-event engine: a future-event list and resource pools with FIFO queues.

Time is in seconds. `Pool` integrates busy units and queue length over time, so utilization and the average queue length are exact
time-weighted values (the way AnyLogic's Seize/Release statistics work).
"""
from __future__ import annotations

import heapq
from collections import deque


class Pool:
    """A resource pool: `capacity` units, a FIFO queue of waiting requests, and time-weighted statistics."""

    __slots__ = ("name", "capacity", "busy", "queue", "_t", "_busy_area", "_queue_area", "_cap_area", "max_queue", "since")

    def __init__(self, name: str, capacity: int):
        self.name, self.capacity, self.busy, self.queue = name, capacity, 0, deque()
        self._t = self.since = 0.0
        self._busy_area = self._queue_area = self._cap_area = 0.0
        self.max_queue = 0

    def _tick(self, now: float) -> None:
        dt = now - self._t
        if dt:
            self._busy_area += self.busy * dt
            self._cap_area += self.capacity * dt   # capacity can change during a live run, so it is integrated too
            self._queue_area += len(self.queue) * dt
            self._t = now

    def take(self, now: float) -> bool:
        """Grab a unit if one is free."""
        self._tick(now)
        if self.busy < self.capacity:
            self.busy += 1
            return True
        return False

    def wait(self, now: float, item) -> None:
        self._tick(now)
        self.queue.append(item)
        self.max_queue = max(self.max_queue, len(self.queue))

    def leave_queue(self, now: float, item) -> bool:
        """Remove a waiting item (it gave up). False if it was not waiting any more."""
        self._tick(now)
        try:
            self.queue.remove(item)
            return True
        except ValueError:
            return False

    def release(self, now: float):
        """Free a unit; returns the next waiting item (which keeps the unit) or None."""
        self._tick(now)
        if self.queue and self.busy <= self.capacity:   # over capacity after a live scale-down: the unit is retired instead of handed on
            return self.queue.popleft()
        self.busy -= 1
        return None

    def spare(self) -> int:
        return max(0, self.capacity - self.busy)

    def reset_stats(self, now: float) -> None:
        """Start measuring afresh (end of the warm-up period)."""
        self._tick(now)
        self._busy_area = self._queue_area = self._cap_area = 0.0
        self.since = self._t = now
        self.max_queue = len(self.queue)

    def utilization(self, now: float) -> float:
        self._tick(now)
        return self._busy_area / self._cap_area if self._cap_area > 0 else 0.0

    def avg_queue(self, now: float) -> float:
        self._tick(now)
        span = now - self.since
        return self._queue_area / span if span > 0 else 0.0


class Scheduler:
    """The future-event list. Events are (time, sequence, kind, payload); the sequence number keeps ties in insertion order."""

    __slots__ = ("now", "_heap", "_seq", "events")

    def __init__(self):
        self.now, self._heap, self._seq, self.events = 0.0, [], 0, 0

    def at(self, t: float, kind: int, payload=None) -> None:
        self._seq += 1
        heapq.heappush(self._heap, (t, self._seq, kind, payload))

    def after(self, dt: float, kind: int, payload=None) -> None:
        self.at(self.now + dt, kind, payload)

    def peek(self) -> float | None:
        return self._heap[0][0] if self._heap else None

    def pop_until(self, limit: float):
        """Yield events in time order up to `limit`, advancing the clock; the clock ends exactly at `limit`."""
        heap = self._heap
        while heap and heap[0][0] <= limit:
            t, _, kind, payload = heapq.heappop(heap)
            self.now = t
            self.events += 1
            yield kind, payload
        self.now = max(self.now, limit)
