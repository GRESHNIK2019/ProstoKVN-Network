# ProstoKVN Network

ProstoKVN Network — Windows network client with smart split routing, subscription support, automatic server selection and GitHub updates.

## Возможности

- Smart / Games / Global маршрутизация.
- Российские доменные зоны `.ru`, `.su`, `.рф` идут напрямую.
- Игры и Ubisoft можно направлять через VPN без полного проксирования Steam.
- Discord и Telegram поддерживаются отдельными процессными правилами.
- Поддержка VLESS, VMess, Trojan, Shadowsocks, Hysteria2, TUIC и VLESS XHTTP/gRPC/WS/REALITY.
- Автоматический выбор и тестирование узлов.
- Управление подписками.
- Автоматическая установка официальных `sing-box` и `Xray-core` при первом запуске.
- Светлая, тёмная и системная тема.
- Проверка новых версий через GitHub Releases.
- Автообновление EXE с проверкой SHA-256.

## Текущая версия

`0.20.0`

## Локальные данные

Настройки, подписки, скачанные ядра и кэш хранятся отдельно от программы:

`%LOCALAPPDATA%\ProstoKVN Network\`

При первом запуске новой версии настройки из предыдущего каталога автоматически переносятся.

## Обновления

Стабильные версии публикуются через GitHub Releases. ProstoKVN Network проверяет наличие новой версии после запуска и позволяет запустить проверку вручную через пункт `Помощь`.

## Сборка

GitHub Actions собирает `ProstoKVNNetwork.exe`, создаёт SHA-256 и публикует Release.

Исходный архив релиза находится в `release_payload/v0.20.0/ProstoKVNNetwork_Source.zip`.
