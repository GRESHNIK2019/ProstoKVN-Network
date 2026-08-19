# ProstoKVN Network

ProstoKVN Network — open-source Windows-клиент для раздельной маршрутизации трафика через VPN. Приложение работает с несколькими группами подписок, проверяет доступные узлы и позволяет направлять выбранные Windows-приложения через VPN без перевода всего трафика в туннель.

## Возможности

- стратегии `Smart`, `Приложения` и `Global`;
- `.ru`, `.su` и `.рф` направляются напрямую;
- пользовательский список EXE-приложений для маршрутизации через VPN;
- отдельная маршрутизация Discord и Telegram, Steam остаётся DIRECT;
- VLESS, VMess, Trojan, Shadowsocks, Hysteria2, TUIC и VLESS XHTTP/gRPC/WS/REALITY;
- несколько HTTPS-проверок, TCP/UDP и оценка стабильности при выборе узла;
- несколько групп подписок с выбором активной группы;
- URL подписок шифруются Windows DPAPI перед записью в настройки;
- атомарное сохранение `settings.json` и резервная копия;
- автоматическая установка официальных `sing-box` и `Xray-core`;
- watchdog VPN-процессов и автоматическое переподключение;
- светлая, тёмная и системная тема;
- проверка обновлений через GitHub Releases;
- проверка SHA-256 и Authenticode перед установкой обновления.

## Структура проекта

- `src/` — исходный код и ресурсы приложения;
- `src/routing.py` — TUN-правила и маршрутизация приложений;
- `src/node_tester.py` — проверка и оценка узлов;
- `src/blocklists.py` — загрузка и кэш списков маршрутизации;
- `src/vpn_runner.py` — запуск и остановка sing-box/Xray;
- `src/ui/` — отдельные части интерфейса;
- `scripts/` — локальный запуск, проверка исходников и сборка;
- `tests/` — unit-тесты;
- `docs/` — правила разработки;
- `.github/workflows/build.yml` — Windows-сборка и SignPath pipeline;
- `CODE_SIGNING_POLICY.md` — правила публичной подписи;
- `PRIVACY.md` — политика конфиденциальности;
- `THIRD_PARTY.md` — сторонние компоненты.

## Текущая версия

`0.22.0`

## Запуск из исходников

```bat
scripts\start.bat
```

## Проверка исходников

```bat
python scripts\check_source.py
python -m unittest discover -s tests -p "test_*.py" -v
```

Проверка валидирует UTF-8, синтаксис Python, unit-тесты и совпадение версии между `version.json`, `src/app_config.py` и `src/version_info.txt`.

## Локальная сборка

```bat
scripts\build_exe.bat
```

Готовый файл появится в `dist\ProstoKVNNetwork.exe`.

## GitHub Actions и подпись

Каждый push в `main` собирает CI artifact. Официальный Release создаётся только из тега вида `vX.Y.Z`, если подключён SignPath и полученный EXE проходит проверку Authenticode.

До одобрения проекта SignPath Foundation публичная публикация подписанного EXE в workflow остаётся выключенной. Настройка описана в [`SIGNING.md`](SIGNING.md).

## Системные изменения

Во время работы VPN приложение создаёт TUN-интерфейс и временно изменяет маршрутизацию Windows. Ядра, настройки и служебные файлы хранятся в `%LOCALAPPDATA%\ProstoKVN Network\`.

## Конфиденциальность

В приложении нет встроенной телеметрии и рекламной аналитики. Подробнее: [`PRIVACY.md`](PRIVACY.md).

## Code signing policy

Free code signing provided by SignPath.io, certificate by SignPath Foundation.

Политика подписи: [`CODE_SIGNING_POLICY.md`](CODE_SIGNING_POLICY.md).

- Committers and reviewers: [GRESHNIK2019](https://github.com/GRESHNIK2019)
- Approvers: [GRESHNIK2019](https://github.com/GRESHNIK2019)

## Лицензия

Собственный код ProstoKVN Network распространяется по лицензии **GNU General Public License v3.0 or later** (`GPL-3.0-or-later`). Полный текст находится в [`LICENSE`](LICENSE).

Copyright (C) 2026 GRESHNIK2019.

## Удаление

1. Остановить VPN и закрыть ProstoKVN Network.
2. Удалить `ProstoKVNNetwork.exe`.
3. При необходимости удалить `%LOCALAPPDATA%\ProstoKVN Network\`.
