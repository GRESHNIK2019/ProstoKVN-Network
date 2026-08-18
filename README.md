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

## Версия

Следующий публичный релиз: `0.20.0`.

## Локальные данные

Приложение использует каталог:

`%LOCALAPPDATA%\ProstoKVN Network\`

При первом запуске настройки из предыдущих версий автоматически переносятся.

## Обновления

Стабильные версии публикуются через GitHub Releases. ProstoKVN Network проверяет наличие новой версии после запуска и позволяет запустить проверку вручную через пункт `Помощь`.

## Сборка

Для запуска из исходников требуется Python 3 и зависимости из `requirements.txt`.

Для сборки Windows EXE используется PyInstaller и GitHub Actions.
