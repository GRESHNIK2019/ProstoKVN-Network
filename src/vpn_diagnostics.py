# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""Диагностика состояния VPN-сеанса.

Не управляет процессами. Только собирает безопасное состояние для UI,
логов и аварийных сообщений.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from vpn_state import VpnState


@dataclass(slots=True)
class VpnDiagnostics:
    state: VpnState = VpnState.STOPPED
    started_at: Optional[str] = None
    last_error: str = ""
    singbox_pid: Optional[int] = None
    xray_pid: Optional[int] = None
    tun_ready: bool = False

    def set_state(self, state: VpnState) -> None:
        self.state = state
        if state == VpnState.RUNNING and self.started_at is None:
            self.started_at = datetime.now(timezone.utc).isoformat()

    def fail(self, error: str) -> None:
        self.state = VpnState.FAILED
        self.last_error = error.strip()

    def snapshot(self) -> dict[str, object]:
        return {
            "state": self.state.value,
            "started_at": self.started_at,
            "last_error": self.last_error,
            "singbox_pid": self.singbox_pid,
            "xray_pid": self.xray_pid,
            "tun_ready": self.tun_ready,
        }
