# Smart VPN

Smart VPN — Windows VPN client with smart split routing, subscription support, automatic server selection and GitHub updates.

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

`0.19.0`

## Локальные данные

Настройки, подписки, скачанные ядра и кэш хранятся отдельно от программы:

`%LOCALAPPDATA%\SmartVPN\`

Поэтому обновление программы не удаляет пользовательские настройки.

## Обновления

Стабильные версии публикуются через GitHub Releases. Smart VPN проверяет наличие новой версии после запуска и также позволяет запустить проверку вручную через пункт `Помощь`.

## Сборка

Для запуска из исходников требуется Python 3 и зависимости из `requirements.txt`.

Для сборки Windows EXE используется PyInstaller и GitHub Actions.
