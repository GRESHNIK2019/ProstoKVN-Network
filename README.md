# ProstoKVN Network

ProstoKVN Network — open-source Windows-клиент для раздельной маршрутизации трафика через VPN. Приложение работает с подписками, проверяет доступные узлы и применяет отдельные правила для игр и сервисов.

## Возможности

- стратегии `Smart`, `Games` и `Global`;
- `.ru`, `.su` и `.рф` направляются напрямую;
- отдельная маршрутизация для игр, Ubisoft, Discord и Telegram;
- VLESS, VMess, Trojan, Shadowsocks, Hysteria2, TUIC и VLESS XHTTP/gRPC/WS/REALITY;
- автоматическое тестирование и выбор узла;
- управление подпиской;
- автоматическая установка официальных `sing-box` и `Xray-core`;
- светлая, тёмная и системная тема;
- проверка обновлений через GitHub Releases;
- проверка SHA-256 перед установкой обновления.

## Структура проекта

- `src/` — исходный код и ресурсы приложения;
- `scripts/` — локальный запуск, проверка исходников и сборка;
- `docs/` — правила разработки;
- `.github/workflows/build.yml` — Windows-сборка и SignPath pipeline;
- `CODE_SIGNING_POLICY.md` — правила публичной подписи;
- `PRIVACY.md` — политика конфиденциальности;
- `THIRD_PARTY.md` — сторонние компоненты.

## Текущая версия

`0.21.0`

## Запуск из исходников

```bat
scripts\start.bat
```

## Проверка исходников

```bat
python scripts\check_source.py
```

Проверка валидирует UTF-8, синтаксис Python и совпадение версии между `version.json`, `src/app_config.py` и `src/version_info.txt`.

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
