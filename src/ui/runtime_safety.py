# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from queue import Empty
import threading
import types
from typing import Any

from app_config import STRATEGIES
from blocklists import get_cached_ru_blocklists, update_ru_blocklists
from nodes import Node
from paths import RUNTIME_DIR
from process_manager import PROCESS_MANAGER
from subscriptions import touch_subscription
from vpn_runner import TunRunner


_VPN_EVENT_KINDS = {"started", "stopped"}


def best_working_node(tested: list[Node]) -> Node | None:
    good = [node for node in tested if node.valid and node.https_ms is not None]
    if not good:
        return None
    return max(good, key=lambda node: node.score)


def _state_lock(app) -> threading.RLock:
    lock = getattr(app, "_vpn_state_lock", None)
    if lock is None:
        lock = threading.RLock()
        app._vpn_state_lock = lock
    return lock


def _next_generation(app) -> int:
    app._vpn_generation = int(getattr(app, "_vpn_generation", 0)) + 1
    return app._vpn_generation


def _discard_pending_vpn_events(app) -> None:
    kept: list[tuple[str, object]] = []
    while True:
        try:
            item = app.events.get_nowait()
        except Empty:
            break
        try:
            kind = item[0] if isinstance(item, tuple) and item else ""
            if kind not in _VPN_EVENT_KINDS:
                kept.append(item)
        finally:
            try:
                app.events.task_done()
            except Exception:
                pass
    for item in kept:
        app.events.put(item)


def _runner_for(app, node: Node, route_mode: str) -> TunRunner:
    paths = list(app.blocklist_paths or get_cached_ru_blocklists())
    if route_mode == "smart_ru" and not paths:
        update_ru_blocklists(lambda _text: None)
        paths = get_cached_ru_blocklists()
        app.blocklist_paths = list(paths)
    return TunRunner(
        app.singbox,
        node,
        discord_vpn=True,
        steam_webhelper_vpn=False,
        xray=app.xray,
        blocked_ru_vpn=(route_mode == "smart_ru"),
        blocklist_paths=paths,
        route_mode=route_mode,
        custom_vpn_processes=list(app.custom_vpn_processes),
    )


def _working_selected_node(app) -> Node | None:
    node = getattr(app, "selected_node", None)
    if not isinstance(node, Node):
        return None
    if not node.valid or node.https_ms is None:
        return None
    return node


def _stop_runner_quietly(runner: TunRunner | None) -> None:
    if runner is None:
        return
    try:
        runner.stop()
    except Exception:
        pass


def _cleanup_test_orphans() -> None:
    PROCESS_MANAGER.cleanup_owned_processes(RUNTIME_DIR, tests_only=True)


def _safe_finish(self, tested: list[Node]) -> None:
    self.busy = False
    self.test_btn.configure(state="normal")
    all_sorted = sorted(tested, key=lambda node: node.score, reverse=True)
    self.tested_nodes = all_sorted
    active_subscription = self._active_subscription()
    if active_subscription:
        touch_subscription(active_subscription)
        self._save_settings()

    threading.Thread(target=_cleanup_test_orphans, daemon=True).start()

    best = best_working_node(all_sorted)
    self.selected_node = best
    self._refresh_tree()
    if best is None:
        self.best_var.set("Узел: —")
        self.start_btn.configure(state="disabled")
        self.apply_btn.configure(state="disabled")
        self.status_var.set(f"Рабочих узлов нет · проверено {len(all_sorted)}")
        self._append_log("[SUB] Рабочие узлы не найдены; FAIL-узел автоматически не выбирается")
        self._refresh_header_summary()
        return

    ping = f"{best.https_ms:.0f} ms"
    udp_text = "OK" if best.udp_ok else "FAIL"
    self.best_var.set(f"Выбран: {best.name} | {best.stack_label()} | {ping}")
    self.status_var.set(f"Подписка загружена · {len(self.nodes)} узлов")
    self.start_btn.configure(state="normal")
    self._append_log(f"[SUB] Найден лучший узел: {best.name} | {ping} | UDP {udp_text}")
    self._refresh_header_summary()


def _safe_start_vpn(self) -> None:
    node = _working_selected_node(self)
    if node is None:
        self.start_btn.configure(state="disabled")
        self.status_var.set("Нет рабочего узла для запуска VPN")
        try:
            from tkinter import messagebox
            messagebox.showwarning(
                "ProstoKVN Network",
                "Сначала дождись успешной проверки узла. Узел со статусом FAIL не запускается автоматически.",
            )
        except Exception:
            pass
        return

    self._auto_find_cores()
    if not self.singbox:
        try:
            from tkinter import messagebox
            messagebox.showerror("ProstoKVN Network", "Не найден совместимый sing-box.exe.")
        except Exception:
            pass
        return

    self._save_settings()
    route_mode = self.strategy_key_var.get()
    self.status_var.set("Запускаю VPN...")
    self.start_btn.configure(state="disabled")
    self.apply_btn.configure(state="disabled")
    self.stop_btn.configure(state="normal")
    self._append_log(f"[VPN] Запуск: {node.name}")
    self._refresh_header_summary()

    with _state_lock(self):
        generation = _next_generation(self)
        _discard_pending_vpn_events(self)
        old_runner = self.runner
        old_starting = getattr(self, "_starting_runner", None)
        self.runner = None
        self._starting_runner = None

    _stop_runner_quietly(old_runner)
    if old_starting is not old_runner:
        _stop_runner_quietly(old_starting)

    def worker() -> None:
        runner: TunRunner | None = None
        try:
            with _state_lock(self):
                if generation != self._vpn_generation:
                    return
            runner = _runner_for(self, node, route_mode)
            with _state_lock(self):
                if generation != self._vpn_generation:
                    return
                self._starting_runner = runner

            runner.start()

            obsolete = False
            with _state_lock(self):
                if self._starting_runner is runner:
                    self._starting_runner = None
                if generation != self._vpn_generation:
                    obsolete = True
                else:
                    self.runner = runner
                    self.events.put(("started", (route_mode, node)))
            if obsolete:
                _stop_runner_quietly(runner)
        except Exception as exc:
            _stop_runner_quietly(runner)
            with _state_lock(self):
                if self._starting_runner is runner:
                    self._starting_runner = None
                if generation != self._vpn_generation:
                    return
                self.runner = None
                self.events.put(("stopped", None))
                self.events.put(("error", str(exc)))

    threading.Thread(target=worker, name="ProstoKVN-VPN-Start", daemon=True).start()


def _safe_apply_strategy(self) -> None:
    node = _working_selected_node(self)
    if node is None:
        self.start_btn.configure(state="disabled")
        try:
            from tkinter import messagebox
            messagebox.showwarning("ProstoKVN Network", "Нельзя переключить VPN на узел, который не прошёл проверку.")
        except Exception:
            pass
        return

    self._save_settings()
    route_mode = self.strategy_key_var.get()
    self.status_var.set(f"Применяю стратегию {STRATEGIES[route_mode]}...")
    self.start_btn.configure(state="disabled")
    self.apply_btn.configure(state="disabled")
    self.stop_btn.configure(state="normal")
    self._append_log(f"[VPN] Переключение: {node.name} | {STRATEGIES[route_mode]}")
    self._refresh_header_summary()

    with _state_lock(self):
        generation = _next_generation(self)
        _discard_pending_vpn_events(self)
        old_runner = self.runner
        old_starting = getattr(self, "_starting_runner", None)
        self.runner = None
        self._starting_runner = None

    def worker() -> None:
        runner: TunRunner | None = None
        try:
            _stop_runner_quietly(old_runner)
            if old_starting is not old_runner:
                _stop_runner_quietly(old_starting)
            with _state_lock(self):
                if generation != self._vpn_generation:
                    return
            runner = _runner_for(self, node, route_mode)
            with _state_lock(self):
                if generation != self._vpn_generation:
                    return
                self._starting_runner = runner

            runner.start()

            obsolete = False
            with _state_lock(self):
                if self._starting_runner is runner:
                    self._starting_runner = None
                if generation != self._vpn_generation:
                    obsolete = True
                else:
                    self.runner = runner
                    self.events.put(("started", (route_mode, node)))
            if obsolete:
                _stop_runner_quietly(runner)
        except Exception as exc:
            _stop_runner_quietly(runner)
            with _state_lock(self):
                if self._starting_runner is runner:
                    self._starting_runner = None
                if generation != self._vpn_generation:
                    return
                self.runner = None
                self.applied_strategy_key = None
                self.applied_node = None
                self.events.put(("stopped", None))
                self.events.put(("error", str(exc)))

    threading.Thread(target=worker, name="ProstoKVN-VPN-Switch", daemon=True).start()


def _safe_stop_vpn(self, silent: bool = False) -> None:
    self._auto_reconnect_attempted = False
    with _state_lock(self):
        _next_generation(self)
        _discard_pending_vpn_events(self)
        runner = self.runner
        starting = getattr(self, "_starting_runner", None)
        self.runner = None
        self._starting_runner = None

    _stop_runner_quietly(runner)
    if starting is not runner:
        _stop_runner_quietly(starting)
    if not silent:
        self.events.put(("stopped", None))


def _safe_on_close(self) -> None:
    """Финальный выход: настройки → VPN → tray → все дочерние cores → Tk."""
    if getattr(self, "_closing_app", False):
        return
    self._closing_app = True
    try:
        self._save_settings()
    except Exception:
        pass
    try:
        self.stop_vpn(silent=True)
    except Exception:
        pass
    controller = getattr(self, "_tray_controller", None)
    if controller is not None:
        try:
            controller.stop(final=True)
        except Exception:
            pass
    try:
        # Сюда попадают и тестовые процессы, если пользователь закрыл приложение
        # прямо во время проверки подписки.
        PROCESS_MANAGER.stop_all()
    except Exception:
        pass
    try:
        self.destroy()
    except Exception:
        pass


def _cleanup_previous_orphans(app: Any) -> None:
    count = PROCESS_MANAGER.cleanup_owned_processes(RUNTIME_DIR, tests_only=False)
    if count > 0:
        try:
            app.events.put(("cleanup_info", count))
        except Exception:
            pass


def install_runtime_safety(app: Any) -> None:
    if getattr(app, "_runtime_safety_installed", False):
        return

    app._runtime_safety_installed = True
    app._vpn_generation = 0
    app._vpn_state_lock = threading.RLock()
    app._starting_runner = None
    app._closing_app = False

    threading.Thread(target=_cleanup_previous_orphans, args=(app,), name="ProstoKVN-Orphan-Cleanup", daemon=True).start()

    app._finish = types.MethodType(_safe_finish, app)
    app.start_vpn = types.MethodType(_safe_start_vpn, app)
    app.apply_strategy = types.MethodType(_safe_apply_strategy, app)
    app.stop_vpn = types.MethodType(_safe_stop_vpn, app)
    app.on_close = types.MethodType(_safe_on_close, app)
