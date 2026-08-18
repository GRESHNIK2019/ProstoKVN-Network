# Smart VPN

Smart VPN — Windows VPN client with smart split routing, subscription support, automatic server selection and GitHub updates.

## Возможности

- Smart / Games / Global маршрутизация.
- Российские доменные зоны `.ru`, `.su`, `.рф` идут напрямую.
- The Crew Motorfest / Ubisoft можно направлять через VPN без полного проксирования Steam.
- Discord и Telegram поддерживаются отдельными процессными правилами.
- Поддержка VLESS, VMess, Trojan, Shadowsocks, Hysteria2, TUIC и VLESS XHTTP/gRPC/WS/REALITY.
- Автоматический выбор и тестирование узлов.
- Управление подписками.
- Автоматическая установка официальных `sing-box` и `Xray-core` при первом запуске.
- Светлая, тёмная и системная тема.

## Текущая версия

`0.18.0`

## Структура

- `src/` — исходный код Smart VPN.
- `scripts/` — вспомогательные Windows-скрипты.
- `version.json` — метаданные текущей версии для автообновления.
- `.github/workflows/` — сборка и публикация релизов.

## Локальные данные

Подписки, настройки, скачанные ядра и кэш **не хранятся в репозитории**. Приложение использует `%LOCALAPPDATA%\MotorfestVPN_AutoSelector\`.

## Сборка

Для запуска из исходников требуется Python 3 и зависимости из `requirements.txt`.

Для сборки EXE можно использовать `scripts/build_exe.bat` или GitHub Actions.
