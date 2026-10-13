"""FIFO tickets; events and exact owner exit drive admission, never elapsed age."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
import uuid

from .native import Native, Mutex, PREFIX


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix("." + uuid.uuid4().hex + ".pending")
    try:
        with pending.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(pending, path)
    finally:
        pending.unlink(missing_ok=True)


def default_root(native=None):
    n = native or Native()
    return Path(os.environ["LOCALAPPDATA"]) / "Tools/windows-elevation-gate/state" / f"session-{n.session()}"


class Queue:
    def __init__(self, root=None, namespace=PREFIX, *, native=None):
        self.n = native or Native()
        self.root = Path(root) if root is not None else default_root(self.n)
        self.namespace = namespace
        self.ticket = None
        self.event = None

    def lock(self):
        return Mutex(self.namespace + ".Queue", self.n)

    def read(self):
        path = self.root / "queue.json"
        if not path.exists():
            return {"schema": 1, "next": 1, "tickets": [], "history": []}
        state = json.loads(path.read_text(encoding="utf-8"))
        if (not isinstance(state, dict) or state.get("schema") != 1 or
                type(state.get("next")) is not int or state["next"] < 1 or
                not isinstance(state.get("tickets"), list) or not isinstance(state.get("history"), list)):
            raise ValueError("Invalid elevation queue; refusing to reset it")
        numbers, ids = [], set()
        for ticket in state["tickets"]:
            if (not isinstance(ticket, dict) or not re.fullmatch(r"[0-9a-f]{32}", str(ticket.get("id", ""))) or
                    any(type(ticket.get(k)) is not int or ticket[k] < 1 for k in ("number", "pid", "ticks")) or
                    ticket.get("phase") not in ("queued", "explaining", "uac", "launched")):
                raise ValueError("Invalid elevation ticket")
            numbers.append(ticket["number"])
            ids.add(ticket["id"])
        if len(ids) != len(numbers) or numbers != sorted(set(numbers)) or (numbers and numbers[-1] >= state["next"]):
            raise ValueError("Invalid FIFO ordering")
        return state

    def save(self, state):
        state["history"] = state["history"][-100:]
        atomic_json(self.root / "queue.json", state)

    def signal_all(self, state):
        for ticket in state["tickets"]:
            event = self.n.event(self.namespace + ".Ticket." + ticket["id"])
            try:
                self.n.signal(event)
            finally:
                self.n.close(event)

    def alive(self, ticket):
        handle, _ = self.n.process(ticket["pid"], ticket["ticks"])
        self.n.close(handle)
        return handle is not None

    def prune(self, state):
        retained = []
        for ticket in state["tickets"]:
            if self.alive(ticket) or ticket["phase"] == "uac":
                retained.append(ticket)
            else:
                state["history"].append({**ticket, "outcome": "owner_exited"})
                if ticket["phase"] in ("queued", "explaining"):
                    # No UAC launch occurred in these phases. Exact helper metadata only.
                    (self.root / "requests" / (ticket["id"] + ".json")).unlink(missing_ok=True)
        changed = retained != state["tickets"]
        state["tickets"] = retained
        return changed

    def register(self, labels):
        if self.ticket is not None:
            raise RuntimeError("Request already registered")
        handle, ticks = self.n.process(os.getpid())
        self.n.close(handle)
        ticket = {"id": uuid.uuid4().hex, "pid": os.getpid(), "ticks": ticks,
                  "phase": "queued", "task": labels["task"], "thread_name": labels["thread_name"]}
        self.event = self.n.event(self.namespace + ".Ticket." + ticket["id"])
        with self.lock():
            state = self.read()
            self.prune(state)
            ticket["number"] = state["next"]
            state["next"] += 1
            state["tickets"].append(ticket)
            self.save(state)
            self.ticket = ticket
            self.signal_all(state)
        return ticket

    def wait_turn(self):
        while True:
            with self.lock():
                state = self.read()
                if self.prune(state):
                    self.save(state)
                    self.signal_all(state)
                if not any(t["id"] == self.ticket["id"] for t in state["tickets"]):
                    raise RuntimeError("Own ticket missing; refusing to launch")
                head = state["tickets"][0]
                if head["id"] == self.ticket["id"]:
                    return
                if not self.n.k.ResetEvent(self.event):
                    raise OSError("Cannot arm elevation queue event")
                handle, _ = self.n.process(head["pid"], head["ticks"])
                recovery = handle is None and head["phase"] == "uac"
            try:
                if recovery:
                    print(json.dumps({"state": "owner_recovery_required", "request_id": head["id"]}),
                          file=sys.stderr, flush=True)
                    self.n.wait(self.event)
                elif handle:
                    self.n.wait(self.event, handle)
            finally:
                self.n.close(handle)

    def phase(self, phase):
        with self.lock():
            state = self.read()
            ticket = next(t for t in state["tickets"] if t["id"] == self.ticket["id"])
            ticket["phase"] = phase
            self.ticket = dict(ticket)
            self.save(state)

    def release(self, outcome):
        try:
            if self.ticket:
                with self.lock():
                    state = self.read()
                    state["tickets"] = [t for t in state["tickets"] if t["id"] != self.ticket["id"]]
                    state["history"].append({**self.ticket, "outcome": outcome})
                    self.prune(state)
                    self.save(state)
                    self.signal_all(state)
                self.ticket = None
        finally:
            self.n.close(self.event)
            self.event = None

    def status(self):
        with self.lock():
            state = self.read()
            for ticket in state["tickets"]:
                ticket["owner_alive"] = self.alive(ticket)
                ticket["recovery_required"] = not ticket["owner_alive"] and ticket["phase"] == "uac"
        return {"ok": True, "operation": "status", "ordering": "fifo_registration",
                "pending": len(state["tickets"]), "tickets": state["tickets"],
                "history": state["history"], "read_only": True}

    def recover(self, request_id, confirmed):
        if not confirmed:
            raise ValueError("Explicit confirmation that the old dialog/UAC is settled is required")
        with self.lock():
            state = self.read()
            ticket = next((t for t in state["tickets"] if t["id"] == request_id), None)
            if not ticket or self.alive(ticket) or ticket["phase"] != "uac":
                raise ValueError("Recovery is only for an exact dead owner with an ambiguous UAC phase")
            state["tickets"].remove(ticket)
            state["history"].append({**ticket, "outcome": "operator_confirmed_prompt_settled"})
            self.save(state)
            self.signal_all(state)
        return {"ok": True, "operation": "recover", "request_id": request_id}
