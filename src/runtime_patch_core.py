"""Fail-closed runtime policy for the FA507NV EC gate.

This module contains the repair decision and rollback logic only.  It does not
open a driver, guess an EC address, or write hardware by itself.  A verified
adapter must implement read_xdata8/write_xdata8 and provide independent power
evidence before this controller can arm.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol


GPD0_XDATA = 0x1604
GPD0_MASK = 0x01


class EcAdapter(Protocol):
    verified_read: bool
    verified_write: bool

    def read_xdata8(self, address: int) -> int: ...

    def write_xdata8(self, address: int, value: int) -> None: ...


class PatchState(str, Enum):
    IDLE = "idle"
    ACTIVE = "active"
    ROLLING_BACK = "rolling_back"
    BLOCKED = "blocked"
    FAILED = "failed"


@dataclass(frozen=True)
class Evidence:
    """One synchronized sample from EC, UCSI/PD and the charger path."""

    timestamp_s: float
    protocol_attached: bool
    rdo: int | None
    vbus_mv: int | None
    input_valid: bool
    protection_fault: bool
    charger_path_ready: bool
    battery_net_input_mw: int | None
    gpd0: int | None


@dataclass(frozen=True)
class Decision:
    allow: bool
    reasons: tuple[str, ...] = ()


@dataclass
class PatchPolicy:
    vbus_min_mv: int = 4000
    no_input_timeout_s: float = 8.0
    max_active_s: float = 60.0


@dataclass
class PatchController:
    adapter: EcAdapter
    policy: PatchPolicy = field(default_factory=PatchPolicy)
    state: PatchState = PatchState.IDLE
    original_xdata: int | None = None
    started_s: float | None = None
    last_positive_input_s: float | None = None
    reason: str = ""

    def decide(self, evidence: Evidence) -> Decision:
        reasons: list[str] = []
        if not getattr(self.adapter, "verified_read", False):
            reasons.append("EC read adapter is not verified")
        if not getattr(self.adapter, "verified_write", False):
            reasons.append("EC write adapter is not verified")
        if not evidence.protocol_attached:
            reasons.append("protocol is not attached")
        if evidence.vbus_mv is None or evidence.vbus_mv < self.policy.vbus_min_mv:
            reasons.append("physical VBUS is absent or too low")
        if not evidence.input_valid:
            reasons.append("input path is not valid")
        if evidence.protection_fault:
            reasons.append("OVP/OCP/UVLO/OTP fault is active")
        if not evidence.charger_path_ready:
            reasons.append("charger path is not ready")
        # A zero RDO is permitted only when the physical input and charger path
        # are independently valid; this is the exact low-power failure mode.
        return Decision(not reasons, tuple(reasons))

    def arm(self, evidence: Evidence) -> Decision:
        decision = self.decide(evidence)
        if not decision.allow:
            self.state = PatchState.BLOCKED
            self.reason = "; ".join(decision.reasons)
            return decision
        try:
            current = self.adapter.read_xdata8(GPD0_XDATA) & 0xFF
            self.original_xdata = current
            self.adapter.write_xdata8(GPD0_XDATA, current | GPD0_MASK)
            readback = self.adapter.read_xdata8(GPD0_XDATA) & 0xFF
            if not (readback & GPD0_MASK):
                raise RuntimeError("GPD0 readback stayed low")
        except Exception as exc:
            self.state = PatchState.FAILED
            self.reason = f"arm failed: {exc}"
            return Decision(False, (self.reason,))
        self.state = PatchState.ACTIVE
        self.started_s = evidence.timestamp_s
        self.last_positive_input_s = evidence.timestamp_s if (evidence.battery_net_input_mw or 0) > 0 else None
        self.reason = "GPD0 armed and read back high"
        return Decision(True)

    def tick(self, evidence: Evidence) -> Decision:
        if self.state != PatchState.ACTIVE:
            return Decision(False, (f"controller is {self.state.value}",))
        if self.started_s is not None and evidence.timestamp_s - self.started_s > self.policy.max_active_s:
            self.restore("maximum active window elapsed")
            return Decision(False, (self.reason,))
        if (evidence.battery_net_input_mw or 0) > 0:
            self.last_positive_input_s = evidence.timestamp_s
        unsafe = self.decide(evidence)
        # Once active, a transient RDO change is tolerated, but physical input,
        # protection and charger-path validity are never bypassed.
        hard_fault = (
            not evidence.input_valid
            or evidence.protection_fault
            or not evidence.charger_path_ready
            or evidence.vbus_mv is None
            or evidence.vbus_mv < self.policy.vbus_min_mv
            or not evidence.protocol_attached
        )
        if hard_fault:
            self.restore("hard safety condition lost")
            return Decision(False, (self.reason,))
        if self.last_positive_input_s is None or evidence.timestamp_s - self.last_positive_input_s > self.policy.no_input_timeout_s:
            self.restore("no positive battery input within watchdog window")
            return Decision(False, (self.reason,))
        try:
            current = self.adapter.read_xdata8(GPD0_XDATA) & 0xFF
            if not (current & GPD0_MASK):
                self.adapter.write_xdata8(GPD0_XDATA, current | GPD0_MASK)
                readback = self.adapter.read_xdata8(GPD0_XDATA) & 0xFF
                if not (readback & GPD0_MASK):
                    raise RuntimeError("GPD0 re-arm readback stayed low")
        except Exception as exc:
            self.restore(f"re-arm failed: {exc}")
            return Decision(False, (self.reason,))
        return Decision(True)

    def restore(self, reason: str = "manual restore") -> None:
        self.state = PatchState.ROLLING_BACK
        self.reason = reason
        if self.original_xdata is not None and getattr(self.adapter, "verified_write", False):
            try:
                self.adapter.write_xdata8(GPD0_XDATA, self.original_xdata & 0xFF)
            except Exception as exc:
                self.reason = f"rollback failed: {exc}"
                self.state = PatchState.FAILED
                return
        self.state = PatchState.IDLE
        self.started_s = None
        self.last_positive_input_s = None


class MemoryAdapter:
    """Test adapter only; never used by the production backend."""

    verified_read = True
    verified_write = True

    def __init__(self, value: int = 0) -> None:
        self.value = value & 0xFF
        self.writes: list[tuple[int, int]] = []

    def read_xdata8(self, address: int) -> int:
        assert address == GPD0_XDATA
        return self.value

    def write_xdata8(self, address: int, value: int) -> None:
        assert address == GPD0_XDATA
        self.value = value & 0xFF
        self.writes.append((address, self.value))
