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

## Системные изменения

Во время работы VPN приложение создаёт TUN-интерфейс и временно изменяет маршрутизацию Windows. Ядра и служебные файлы хранятся в:

`%LOCALAPPDATA%\ProstoKVN Network\`

## Текущая версия

`0.20.0`

## Лицензия

ProstoKVN Network распространяется по лицензии **GNU General Public License v3.0 or later** (`GPL-3.0-or-later`). См. [`LICENSE`](LICENSE).

Copyright (C) 2026 GRESHNIK2019.

## Конфиденциальность

В приложении нет телеметрии и рекламной аналитики. Подробности: [`PRIVACY.md`](PRIVACY.md).

## Code signing policy

Free code signing provided by SignPath.io, certificate by SignPath Foundation.

Политика подписи и роли проекта: [`CODE_SIGNING_POLICY.md`](CODE_SIGNING_POLICY.md).

- Committers and reviewers: [GRESHNIK2019](https://github.com/GRESHNIK2019)
- Approvers: [GRESHNIK2019](https://github.com/GRESHNIK2019)

## Сборка

GitHub Actions собирает `ProstoKVNNetwork.exe` на GitHub-hosted Windows runner. До подключения SignPath результат доступен как CI artifact. После одобрения OSS-подписки публичный Release должен публиковаться только после успешной проверки Authenticode-подписи.

Исходный архив текущего релиза хранится в `release_payload/v0.20.0/` и восстанавливается GitHub Actions перед сборкой.

## Удаление

Приложение портативное и не использует отдельный Windows Installer. Для полного удаления:

1. остановите VPN и закройте ProstoKVN Network;
2. удалите `ProstoKVNNetwork.exe`;
3. при необходимости удалите `%LOCALAPPDATA%\ProstoKVN Network\`.
