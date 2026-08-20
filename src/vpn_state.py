# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""Состояния жизненного цикла VPN-сеанса.

Используется для исключения неоднозначных состояний между UI,
watchdog и менеджером процессов.
"""

from __future__ import annotations

from enum import Enum


class VpnState(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    FAILED = "failed"


_ALLOWED = {
    VpnState.STOPPED: {VpnState.STARTING},
    VpnState.STARTING: {VpnState.RUNNING, VpnState.FAILED, VpnState.STOPPING},
    VpnState.RUNNING: {VpnState.STOPPING, VpnState.FAILED},
    VpnState.STOPPING: {VpnState.STOPPED, VpnState.FAILED},
    VpnState.FAILED: {VpnState.STARTING, VpnState.STOPPING, VpnState.STOPPED},
}


class VpnStateMachine:
    def __init__(self) -> None:
        self._state = VpnState.STOPPED

    @property
    def state(self) -> VpnState:
        return self._state

    def move(self, target: VpnState) -> None:
        if target == self._state:
            return
        if target not in _ALLOWED[self._state]:
            raise RuntimeError(
                f"Недопустимый переход VPN состояния: {self._state.value} -> {target.value}"
            )
        self._state = target
