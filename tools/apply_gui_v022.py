# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
from pathlib import Path
import textwrap

ROOT = Path(__file__).resolve().parents[1]
GUI_PATH = ROOT / "src" / "ProstoKVNNetwork.pyw"


def class_method_range(source: str, method_name: str) -> tuple[int, int]:
    tree = ast.parse(source)
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != "App":
            continue
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == method_name:
                if child.end_lineno is None:
                    raise RuntimeError(f"Нет end_lineno для {method_name}")
                return child.lineno - 1, child.end_lineno
    raise RuntimeError(f"Метод App.{method_name} не найден")


def replace_method(source: str, method_name: str, new_source: str) -> str:
    start, end = class_method_range(source, method_name)
    lines = source.splitlines(keepends=True)
    method = textwrap.indent(textwrap.dedent(new_source).strip("\n"), "    ") + "\n"
    return "".join(lines[:start]) + method + "".join(lines[end:])


def remove_method(source: str, method_name: str) -> str:
    start, end = class_method_range(source, method_name)
    lines = source.splitlines(keepends=True)
    return "".join(lines[:start]) + "".join(lines[end:])


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: ожидалось 1 совпадение, найдено {count}")
    return source.replace(old, new, 1)


def main() -> None:
    source = GUI_PATH.read_text(encoding="utf-8")
    if "class App(ThemeMixin, SubscriptionMixin, tk.Tk):" in source:
        print("GUI v0.22 уже обновлён")
        return

    old_imports = '''from core import (
    TunRunner, blocklists_age_seconds, get_cached_ru_blocklists, is_admin,
    test_node, update_ru_blocklists,
)
from cores import find_singbox_binary, find_xray_binary, install_official_cores
from nodes import Node, download_subscription
from paths import SETTINGS_PATH
from updater import check_latest_release, download_update, launch_self_updater
'''
    new_imports = '''from blocklists import blocklists_age_seconds, get_cached_ru_blocklists, update_ru_blocklists
from cores import find_singbox_binary, find_xray_binary, install_official_cores
from node_tester import test_node
from nodes import Node, download_subscription
from paths import SETTINGS_PATH
from routing import normalize_process_names
from settings_store import load_settings, save_settings
from subscriptions import dump_subscriptions, load_subscriptions, touch_subscription
from ui.subscriptions import SubscriptionMixin
from ui.theme import ThemeMixin
from updater import check_latest_release, download_update, launch_self_updater
from vpn_runner import TunRunner, is_admin
'''
    source = replace_once(source, old_imports, new_imports, "imports")
    source = replace_once(source, "class App(tk.Tk):", "class App(ThemeMixin, SubscriptionMixin, tk.Tk):", "App bases")

    source = replace_once(
        source,
        "        self.blocklist_paths = get_cached_ru_blocklists()\n\n        self.url_var = tk.StringVar()\n",
        "        self.blocklist_paths = get_cached_ru_blocklists()\n"
        "        self.subscriptions = []\n"
        "        self.active_subscription_id = ''\n"
        "        self.custom_vpn_processes: list[str] = []\n"
        "        self._auto_reconnect_attempted = False\n\n"
        "        self.url_var = tk.StringVar()\n",
        "state fields",
    )
    source = replace_once(
        source,
        "        self.block_var = tk.StringVar(value='Списки: —')\n        self.admin_var = tk.StringVar(value='Admin ✓' if is_admin() else 'Admin ✕')\n",
        "        self.block_var = tk.StringVar(value='Списки: —')\n"
        "        self.custom_apps_var = tk.StringVar(value='Приложения VPN: —')\n"
        "        self.engine_var = tk.StringVar(value='Ядро: —')\n"
        "        self.auto_reconnect_var = tk.BooleanVar(value=True)\n"
        "        self.admin_var = tk.StringVar(value='Admin ✓' if is_admin() else 'Admin ✕')\n",
        "UI vars",
    )
    source = replace_once(
        source,
        "        self.after(1500, self._poll_system_theme)\n",
        "        self.after(1500, self._poll_system_theme)\n        self.after(1800, self._poll_runner_health)\n",
        "watchdog schedule",
    )

    for method in (
        "_resolved_theme",
        "_style",
        "_sync_titlebar_theme",
        "_set_theme_mode",
        "_refresh_theme_buttons",
        "_poll_system_theme",
        "_subscription_info_text",
        "_refresh_subscription_info",
        "_masked_url",
        "open_subscription_manager",
        "_refresh_subscription_list",
        "open_subscription_editor",
        "refresh_current_subscription_from_manager",
    ):
        source = remove_method(source, method)

    load_settings_method = '''
    def _load_settings(self):
        data = load_settings(SETTINGS_PATH)
        self.subscriptions, self.active_subscription_id = load_subscriptions(data)
        self._load_active_subscription_vars()

        self.singbox_var.set(str(data.get('singbox_path') or ''))
        self.xray_var.set(str(data.get('xray_path') or ''))

        strategy = str(data.get('route_strategy') or 'smart_ru')
        self.strategy_key_var.set(strategy if strategy in STRATEGIES else 'smart_ru')

        theme = str(data.get('theme_mode') or 'system')
        self.theme_mode_var.set(theme if theme in THEME_LABELS else 'system')

        self.custom_vpn_processes = normalize_process_names(data.get('custom_vpn_processes') or [])
        self.auto_reconnect_var.set(bool(data.get('auto_reconnect', True)))
        self._refresh_custom_apps_label()
'''
    source = replace_method(source, "_load_settings", load_settings_method)

    save_settings_method = '''
    def _save_settings(self):
        self._store_active_subscription_from_vars()
        data = {
            'subscriptions': dump_subscriptions(self.subscriptions),
            'active_subscription_id': self.active_subscription_id,
            'singbox_path': self.singbox_var.get().strip(),
            'xray_path': self.xray_var.get().strip(),
            'route_strategy': self.strategy_key_var.get(),
            'theme_mode': self.theme_mode_var.get(),
            'custom_vpn_processes': list(self.custom_vpn_processes),
            'auto_reconnect': bool(self.auto_reconnect_var.get()),
            'test_limit': 48,
        }
        try:
            save_settings(SETTINGS_PATH, data)
        except Exception as exc:
            if hasattr(self, 'logbox'):
                self._append_log(f'[SETTINGS] Ошибка сохранения: {exc}')
'''
    source = replace_method(source, "_save_settings", save_settings_method)

    autoload_method = '''
    def _autoload_saved_subscription(self):
        item = self._active_subscription()
        if not item or not item.enabled:
            return
        url = item.url.strip()
        if url.startswith(('http://', 'https://')) and not self.busy and not (self.runner and self.runner.running()):
            self.url_var.set(url)
            self.status_var.set('Автоматически загружаю сохранённую подписку...')
            self._refresh_header_summary()
            self._append_log(f'[SUB] Автоматическая загрузка: {item.name}')
            self.start_test(auto=True)
'''
    source = replace_method(source, "_autoload_saved_subscription", autoload_method)

    build_runner_method = '''
    def _build_runner(self):
        route_mode = self.strategy_key_var.get()
        paths = list(self.blocklist_paths or get_cached_ru_blocklists())
        if route_mode == 'smart_ru' and not paths:
            update_ru_blocklists(lambda _x: None)
            paths[:] = get_cached_ru_blocklists()
        return TunRunner(
            self.singbox,
            self.selected_node,
            discord_vpn=True,
            steam_webhelper_vpn=False,
            xray=self.xray,
            blocked_ru_vpn=(route_mode == 'smart_ru'),
            blocklist_paths=paths,
            route_mode=route_mode,
            custom_vpn_processes=self.custom_vpn_processes,
        )
'''
    source = replace_method(source, "_build_runner", build_runner_method)

    source = source.replace(
        "        good = [n for n in tested if n.valid and n.udp_ok and n.https_ms is not None]\n",
        "        good = [n for n in tested if n.valid and n.https_ms is not None]\n",
        1,
    )
    source = replace_once(
        source,
        "        self.tested_nodes = all_sorted\n        best = good[0] if good else (all_sorted[0] if all_sorted else None)\n",
        "        self.tested_nodes = all_sorted\n"
        "        active_subscription = self._active_subscription()\n"
        "        if active_subscription:\n"
        "            touch_subscription(active_subscription)\n"
        "            self._save_settings()\n"
        "        best = good[0] if good else (all_sorted[0] if all_sorted else None)\n",
        "subscription touch",
    )

    source = replace_once(
        source,
        "            self.route_info_var.set(f'{active_node.stack_label()} · {ping} · {udp}')\n",
        "            self.route_info_var.set(f'{active_node.stack_label()} · {ping} · {udp}')\n"
        "            self.engine_var.set(f'Ядро: {active_node.engine_label()}')\n",
        "engine active",
    )
    source = replace_once(
        source,
        "            self.node_info_var.set('—')\n            self.route_info_var.set('—')\n",
        "            self.node_info_var.set('—')\n            self.route_info_var.set('—')\n            self.engine_var.set('Ядро: —')\n",
        "engine empty",
    )

    source = replace_once(
        source,
        "        self.bottom_left = tk.Label(bottom, text='Локальный: mixed:10808', bg=p['card'], fg=p['secondary'], font=('Segoe UI', 9), padx=10, pady=7)\n"
        "        self.bottom_left.pack(side='left')\n"
        "        self.bottom_center = tk.Label(bottom, text='TUN: управляется ProstoKVN Network', bg=p['card'], fg=p['secondary'], font=('Segoe UI', 9), padx=10, pady=7)\n",
        "        self.bottom_left = tk.Label(bottom, text='TUN: system · MTU 1400', bg=p['card'], fg=p['secondary'], font=('Segoe UI', 9), padx=10, pady=7)\n"
        "        self.bottom_left.pack(side='left')\n"
        "        self.bottom_center = tk.Label(bottom, textvariable=self.engine_var, bg=p['card'], fg=p['secondary'], font=('Segoe UI', 9), padx=10, pady=7)\n",
        "bottom status",
    )

    advanced_anchor = "        tk.Label(self.advanced, textvariable=self.block_var, bg=p['card'], fg=p['secondary'], font=('Segoe UI', 9)).grid(row=2, column=2, columnspan=4, sticky='w', pady=(10, 0), padx=(8,0))\n"
    advanced_extra = advanced_anchor + (
        "        tk.Button(self.advanced, text='Приложения VPN', command=self.open_app_manager, bg=p['card2'], fg=p['text'], activebackground=p['segment_hover'], activeforeground=p['text'], relief='flat', bd=0, padx=12, pady=5).grid(row=3, column=0, pady=(10, 0), sticky='w')\n"
        "        tk.Label(self.advanced, textvariable=self.custom_apps_var, bg=p['card'], fg=p['secondary'], font=('Segoe UI', 9)).grid(row=3, column=1, columnspan=3, sticky='w', pady=(10, 0), padx=(8,0))\n"
        "        tk.Checkbutton(self.advanced, text='Автопереподключение', variable=self.auto_reconnect_var, command=self._save_settings, bg=p['card'], fg=p['text'], activebackground=p['card'], activeforeground=p['text'], selectcolor=p['card2'], bd=0).grid(row=3, column=4, columnspan=2, sticky='e', pady=(10, 0))\n"
    )
    source = replace_once(source, advanced_anchor, advanced_extra, "advanced apps")

    source = replace_once(
        source,
        "                    self.applied_strategy_key = str(applied_key)\n",
        "                    self.applied_strategy_key = str(applied_key)\n                    self._auto_reconnect_attempted = False\n",
        "reconnect reset",
    )

    source = replace_once(
        source,
        "    # ---------------- Настройки ----------------\n",
        '''    # ---------------- Приложения и watchdog ----------------
    def _refresh_custom_apps_label(self):
        if not hasattr(self, 'custom_apps_var'):
            return
        if self.custom_vpn_processes:
            preview = ', '.join(self.custom_vpn_processes[:3])
            if len(self.custom_vpn_processes) > 3:
                preview += f' +{len(self.custom_vpn_processes) - 3}'
            self.custom_apps_var.set(f'Приложения VPN: {preview}')
        else:
            self.custom_apps_var.set('Приложения VPN: не выбраны')

    def open_app_manager(self):
        p = self.palette
        window = tk.Toplevel(self)
        window.title('Приложения через VPN')
        window.geometry('560x420')
        window.minsize(500, 360)
        window.configure(bg=p['root'])
        window.transient(self)

        tk.Label(window, text='Эти EXE будут идти через VPN в режимах Smart и «Приложения».', bg=p['root'], fg=p['text'], font=('Segoe UI', 10)).pack(anchor='w', padx=14, pady=(14, 8))
        frame = tk.Frame(window, bg=p['card'], highlightbackground=p['border'], highlightthickness=1)
        frame.pack(fill='both', expand=True, padx=14, pady=(0, 10))
        listbox = tk.Listbox(frame, bg=p['card'], fg=p['text'], selectbackground=p['selection'], relief='flat', bd=0, font=('Segoe UI', 10))
        listbox.pack(fill='both', expand=True, padx=8, pady=8)
        self.app_listbox = listbox
        self._refresh_app_listbox()

        buttons = tk.Frame(window, bg=p['root'])
        buttons.pack(fill='x', padx=14, pady=(0, 14))
        tk.Button(buttons, text='Добавить EXE', command=self._add_vpn_app, bg=p['accent'], fg=p['accent_text'], activebackground=p['accent_hover'], activeforeground=p['accent_text'], relief='flat', bd=0, padx=12, pady=6).pack(side='left')
        tk.Button(buttons, text='Удалить', command=self._remove_vpn_app, bg=p['card2'], fg=p['text'], activebackground=p['segment_hover'], activeforeground=p['text'], relief='flat', bd=0, padx=12, pady=6).pack(side='left', padx=(8, 0))
        tk.Button(buttons, text='Закрыть', command=window.destroy, bg=p['card2'], fg=p['text'], activebackground=p['segment_hover'], activeforeground=p['text'], relief='flat', bd=0, padx=12, pady=6).pack(side='right')

    def _refresh_app_listbox(self):
        listbox = getattr(self, 'app_listbox', None)
        if not listbox or not listbox.winfo_exists():
            return
        listbox.delete(0, 'end')
        for name in self.custom_vpn_processes:
            listbox.insert('end', name)

    def _add_vpn_app(self):
        path = filedialog.askopenfilename(title='Выберите приложение', filetypes=[('Windows EXE', '*.exe')])
        if not path:
            return
        name = Path(path).name
        self.custom_vpn_processes = normalize_process_names(self.custom_vpn_processes + [name])
        self._save_settings()
        self._refresh_custom_apps_label()
        self._refresh_app_listbox()
        self._append_log(f'[ROUTE] Добавлено приложение через VPN: {name}')

    def _remove_vpn_app(self):
        listbox = getattr(self, 'app_listbox', None)
        if not listbox or not listbox.winfo_exists():
            return
        selection = listbox.curselection()
        if not selection:
            return
        name = str(listbox.get(selection[0]))
        self.custom_vpn_processes = [item for item in self.custom_vpn_processes if item.lower() != name.lower()]
        self._save_settings()
        self._refresh_custom_apps_label()
        self._refresh_app_listbox()
        self._append_log(f'[ROUTE] Удалено приложение из VPN: {name}')

    def _poll_runner_health(self):
        runner = self.runner
        if runner and not runner.running():
            reason = runner.failure_reason()
            self.runner = None
            self.applied_strategy_key = None
            self.applied_node = None
            self.start_btn.configure(state='normal' if self.selected_node else 'disabled')
            self.apply_btn.configure(state='disabled')
            self.stop_btn.configure(state='disabled')
            self.status_var.set('VPN неожиданно остановлен')
            self._append_log('[WATCHDOG] VPN-процесс завершился неожиданно')
            if reason:
                self._append_log('[WATCHDOG] ' + reason.replace('\n', ' | '))
            self._refresh_header_summary()

            if self.auto_reconnect_var.get() and self.selected_node and not self._auto_reconnect_attempted:
                self._auto_reconnect_attempted = True
                self.status_var.set('VPN остановлен. Пробую переподключиться...')
                self._append_log('[WATCHDOG] Автоматическое переподключение через 2 секунды')
                self.after(2000, self.start_vpn)

        self.after(1500, self._poll_runner_health)

    # ---------------- Настройки ----------------
''',
        "apps methods",
    )

    source = replace_once(
        source,
        "    def stop_vpn(self, silent: bool = False):\n        runner = self.runner\n",
        "    def stop_vpn(self, silent: bool = False):\n        self._auto_reconnect_attempted = False\n        runner = self.runner\n",
        "stop reconnect reset",
    )

    GUI_PATH.write_text(source, encoding="utf-8", newline="\n")
    ast.parse(source)
    print("GUI v0.22 обновлён")


if __name__ == "__main__":
    main()
