# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path
import queue
import sys
import threading
from typing import Any

from app_config import APP_VERSION


class TrayController:
    """Стабильный системный трей Windows через pystray.

    pystray работает в отдельном потоке, а любые обращения к Tkinter
    выполняются только в главном UI-потоке через очередь команд.
    """

    POLL_MS = 100

    def __init__(self, app: Any) -> None:
        self.app = app
        self._icon: Any | None = None
        self._thread: threading.Thread | None = None
        self._commands: queue.Queue[str] = queue.Queue()
        self._ready = threading.Event()
        self._poll_started = False
        self._stopping = False
        self.last_error = ""
        self._start_command_poller()

    def _start_command_poller(self) -> None:
        if self._poll_started:
            return
        self._poll_started = True
        try:
            self.app.after(self.POLL_MS, self._drain_commands)
        except Exception:
            self._poll_started = False

    def start(self) -> bool:
        if self._icon is not None:
            return True

        self.last_error = ""
        self._ready.clear()
        self._stopping = False

        try:
            import pystray

            image = self._load_icon_image()
            menu = pystray.Menu(
                pystray.MenuItem(
                    "Открыть ProstoKVN Network",
                    self._request_show,
                    default=True,
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Выход", self._request_exit),
            )
            icon = pystray.Icon(
                "ProstoKVNNetwork",
                image,
                f"ProstoKVN Network v{APP_VERSION}",
                menu,
            )
            self._icon = icon
            self._thread = threading.Thread(
                target=self._run_icon,
                args=(icon,),
                name="ProstoKVN-Tray",
                daemon=True,
            )
            self._thread.start()
        except Exception as exc:
            self.last_error = str(exc)
            self._icon = None
            self._thread = None
            return False

        if not self._ready.wait(timeout=3.0):
            self.last_error = self.last_error or "Windows не подтвердил запуск системного трея."
            self.stop(final=False)
            return False

        return self._icon is not None and not self.last_error

    def minimize(self) -> bool:
        """Скрывает окно только после успешного создания tray icon."""
        if not self.start():
            self._tray_failed_fallback()
            return False

        try:
            self.app.withdraw()
            return True
        except Exception as exc:
            self.last_error = str(exc)
            self._tray_failed_fallback()
            return False

    def restore(self) -> None:
        try:
            self.app.deiconify()
            self.app.state("normal")
            self.app.lift()
            self.app.focus_force()
        except Exception:
            pass

    def stop(self, final: bool = True) -> None:
        self._stopping = final
        icon = self._icon
        self._icon = None

        if icon is not None:
            try:
                icon.stop()
            except Exception:
                pass

        thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout=1.5)
        self._thread = None

        if not final:
            self._stopping = False

    def _run_icon(self, icon: Any) -> None:
        try:
            def setup(_icon: Any) -> None:
                try:
                    _icon.visible = True
                except Exception as exc:
                    self.last_error = str(exc)
                finally:
                    self._ready.set()

            icon.run(setup=setup)
        except Exception as exc:
            self.last_error = str(exc)
            self._ready.set()
            if self._icon is icon:
                self._icon = None

    def _request_show(self, _icon: Any = None, _item: Any = None) -> None:
        self._commands.put("show")

    def _request_exit(self, _icon: Any = None, _item: Any = None) -> None:
        self._commands.put("exit")

    def _drain_commands(self) -> None:
        if self._stopping:
            return

        try:
            while True:
                command = self._commands.get_nowait()
                if command == "show":
                    self.restore()
                elif command == "exit":
                    self.stop(final=True)
                    try:
                        self.app.on_close()
                    except Exception:
                        try:
                            self.app.destroy()
                        except Exception:
                            pass
                    return
        except queue.Empty:
            pass

        try:
            self.app.after(self.POLL_MS, self._drain_commands)
        except Exception:
            pass

    def _tray_failed_fallback(self) -> None:
        """Никогда не оставляет приложение скрытым без доступного выхода."""
        self.restore()
        try:
            from tkinter import messagebox

            close_app = messagebox.askyesno(
                "ProstoKVN Network",
                "Не удалось создать иконку системного трея.\n\n"
                f"{self.last_error or 'Неизвестная ошибка трея.'}\n\n"
                "Закрыть приложение полностью?",
                parent=self.app,
            )
            if close_app:
                self.app.on_close()
        except Exception:
            pass

    @staticmethod
    def _load_icon_image() -> Any:
        from PIL import Image

        candidates: list[Path] = []
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            candidates.append(Path(meipass) / "assets" / "ProstoKVNNetwork.ico")
        candidates.append(Path(__file__).resolve().parents[1] / "assets" / "ProstoKVNNetwork.ico")

        for path in candidates:
            try:
                if path.is_file():
                    with Image.open(path) as source:
                        image = source.convert("RGBA")
                    return image.resize((64, 64))
            except Exception:
                continue

        raise RuntimeError("Не найдена иконка ProstoKVNNetwork.ico для системного трея.")
