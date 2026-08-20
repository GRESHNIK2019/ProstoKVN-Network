# ProstoKVN Network — Python Core v2

## Цели пересборки

1. Один протокол не должен ломать другой.
2. UI не должен знать детали Xray/sing-box схем.
3. Ни один дочерний xray/sing-box не должен переживать Stop/Exit/crash приложения.
4. PyInstaller `_MEI` не должен использоваться как runtime-хранилище внешних процессов.
5. Версии ядер должны быть воспроизводимыми и обновляться без замены работающих файлов.
6. FAIL одного узла не должен ломать всю подписку.
7. TUN считается запущенным только после появления реального адаптера.

## Слои

### `nodes.py` — входные форматы

Отвечает за URL/Base64/Clash YAML/sing-box JSON и создаёт `Node`.
Не запускает процессы и не решает, какое ядро использовать.

### `protocol_engine.py` — протокольные правила

Единый источник истины для:

- structural validation;
- engine plan;
- Xray VLESS builder;
- сохранения transport/TLS/REALITY параметров;
- предупреждений о рискованных/сомнительных комбинациях.

### `node_tester.py` — функциональная проверка

Получает уже нормализованный `Node`, поднимает локальный SOCKS и измеряет:

- HTTPS stability;
- latency;
- TCP reachability;
- SOCKS5 UDP.

Процесс теста всегда завершается в `finally`.

### `process_manager.py` — владение процессами

Все дочерние cores создаются только здесь. Менеджер:

- хранит Popen handles;
- на Windows назначает детей в Job Object с KILL_ON_JOB_CLOSE;
- штатно убивает дерево через `taskkill /T /F`;
- умеет чистить только orphan-процессы ProstoKVN по command line наших runtime config;
- не должен массово завершать xray/sing-box других клиентов.

### `vpn_runner.py` — атомарная VPN-сессия

Владеет рабочими процессами текущего соединения:

- optional Xray SOCKS bridge;
- sing-box TUN.

Последовательность запуска:

`validate → cleanup own orphan → runtime files → optional Xray → sing-box check → sing-box run → wait TUN → health monitor`.

Любая ошибка проходит через один rollback `_stop_locked()`.

### `ui/runtime_safety.py` — состояние UI/lifecycle

UI хранит два разных владельца:

- `runner` — уже запущенная сессия;
- `_starting_runner` — сессия, которая ещё находится внутри `start()`.

Generation ID делает результат устаревшего worker недействительным. Поэтому
Stop во время Start не позволяет старому worker позже «воскресить» VPN.

### `ui/tray.py` — системный трей

Tray thread никогда не вызывает Tkinter напрямую. Команды передаются в UI
через queue + `after()`.

Кнопка X скрывает окно только после успешного создания tray icon. Если иконка
не создана, окно остаётся видимым и пользователь сохраняет возможность выйти.

## Runtime data

Всё, чем могут пользоваться внешние процессы, хранится в:

`%LOCALAPPDATA%\ProstoKVN Network\runtime`

а не в `sys._MEIPASS`/`_MEI...`.

Это относится к:

- `active_tun.json`;
- `active_xray.json`;
- рабочим логам;
- test configs/logs.

## Cores

Managed cores устанавливаются side-by-side:

- `%LOCALAPPDATA%\ProstoKVN Network\cores\sing-box-1.13.14\...`
- `%LOCALAPPDATA%\ProstoKVN Network\cores\xray-26.7.28\...`

Старый каталог не переименовывается и не удаляется во время установки новой
версии. Это важно на Windows, где запущенный EXE/сопутствующие файлы могут быть
заблокированы.

Поиск предпочитает exact pinned managed core. Сохранённый explicit path или
ядро из v2rayN используется только когда его распознанная версия совпадает с
проверенной версией приложения.

## Инварианты

- `Node` не мутируется config builder'ом.
- Один рабочий session generation за раз.
- Start не публикует `started`, пока TUN не подтверждён.
- Stop инвалидирует generation до остановки процессов.
- Не выбранный/FAIL Node не стартует автоматически.
- Xray test и Xray working bridge используют один builder.
- В settings layer нет monkey-patch сетевой логики.
- Пользовательские route rules имеют приоритет до общих Smart-правил, кроме
  защиты собственных VPN cores от зацикливания.
- Установка core не использует `/latest`.

## Перед merge в `main`

Обязательная реальная Windows матрица:

1. Hysteria2.
2. VLESS XHTTP + REALITY.
3. VLESS gRPC + REALITY.
4. VLESS WS + TLS.
5. Дополнительно VMess/Trojan/SS/TUIC при наличии тестовых узлов.
6. Smart / Applications / Global.
7. Start → Stop → Start.
8. Переключение узла во время работающего VPN.
9. Stop сразу после Start.
10. X → tray → Open.
11. X → tray → Exit.
12. После node tests нет test xray/sing-box.
13. После Stop нет active xray/sing-box.
14. После Exit нет дочерних cores.
15. Нет предупреждения PyInstaller `Failed to remove temporary directory _MEI...`.
16. Старый сохранённый core path не должен принудительно победить exact pinned managed core.
17. Повреждённый settings.json должен восстановиться из `.bak` или дать безопасные defaults.
