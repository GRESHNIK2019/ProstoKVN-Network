# ProstoKVN Network

ProstoKVN Network — Windows-клиент для раздельной маршрутизации трафика через VPN. Приложение работает с подписками, автоматически проверяет доступные узлы и применяет отдельные правила для игр и сервисов.

## Возможности

- стратегии `Smart`, `Games` и `Global`;
- российские доменные зоны `.ru`, `.su` и `.рф` направляются напрямую;
- отдельная маршрутизация для игр, Ubisoft, Discord и Telegram;
- поддержка VLESS, VMess, Trojan, Shadowsocks, Hysteria2, TUIC и VLESS XHTTP/gRPC/WS/REALITY;
- автоматическое тестирование и выбор узла;
- управление подпиской;
- автоматическая установка официальных `sing-box` и `Xray-core`;
- светлая, тёмная и системная тема;
- проверка новых версий через GitHub Releases;
- проверка SHA-256 перед установкой обновления.

## Структура проекта

- `src/` — исходный код и ресурсы приложения;
- `scripts/` — локальный запуск и сборка;
- `.github/workflows/build.yml` — воспроизводимая Windows-сборка и SignPath;
- `CODE_SIGNING_POLICY.md` — правила публичной подписи;
- `PRIVACY.md` — политика конфиденциальности;
- `THIRD_PARTY.md` — сторонние компоненты.

Временных `release_payload`, base64-частей и дублирующих каталогов сборки в рабочей ветке больше нет.

## Системные изменения

Во время работы VPN приложение создаёт TUN-интерфейс и временно изменяет маршрутизацию Windows. Ядра и служебные файлы хранятся в `%LOCALAPPDATA%\ProstoKVN Network\`.

## Текущая версия

`0.21.0`

## Лицензия

Собственный код ProstoKVN Network распространяется по лицензии **GNU General Public License v3.0 or later** (`GPL-3.0-or-later`). Полный текст находится в [`LICENSE`](LICENSE).

Copyright (C) 2026 GRESHNIK2019.

## Конфиденциальность

В приложении нет телеметрии и рекламной аналитики. Подробнее: [`PRIVACY.md`](PRIVACY.md).

## Code signing policy

Free code signing provided by SignPath.io, certificate by SignPath Foundation.

Политика подписи: [`CODE_SIGNING_POLICY.md`](CODE_SIGNING_POLICY.md).

- Committers and reviewers: [GRESHNIK2019](https://github.com/GRESHNIK2019)
- Approvers: [GRESHNIK2019](https://github.com/GRESHNIK2019)

## Запуск из исходников

```bat
scripts\start.bat
```

## Локальная сборка

```bat
scripts\build_exe.bat
```

GitHub Actions собирает `ProstoKVNNetwork.exe` напрямую из `src/`. Пока SignPath не подключён, EXE доступен как CI artifact. Публичный Release публикуется только после успешной Authenticode-подписи.

## Удаление

1. Остановить VPN и закрыть ProstoKVN Network.
2. Удалить `ProstoKVNNetwork.exe`.
3. При необходимости удалить `%LOCALAPPDATA%\ProstoKVN Network\`.
