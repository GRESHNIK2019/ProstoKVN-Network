# Настройка бесплатной подписи ProstoKVN Network

Используем **SignPath Foundation** — бесплатную программу code signing для подходящих open-source проектов.

## 1. Подготовить репозиторий

Перед заявкой проверить:

- репозиторий публичный;
- есть нормальный README;
- есть опубликованный релиз;
- весь собственный код проекта открыт;
- выбрана OSI-approved лицензия;
- в релиз не попадает proprietary-код.

## 2. Выбрать лицензию

Для бесплатной программы SignPath Foundation лицензия обязательна.

Для ProstoKVN Network разумные варианты:

- `GPL-3.0` — производные версии при распространении тоже должны оставаться открытыми;
- `MIT` — максимально свободное повторное использование, включая закрытые коммерческие проекты.

Лицензию не добавляем автоматически: владелец проекта должен выбрать её осознанно.

## 3. Подать заявку SignPath Foundation

Подать заявку на бесплатный Open Source Code Signing и указать репозиторий:

`GRESHNIK2019/ProstoKVN-Network`

SignPath проверяет, что проект соответствует условиям OSS-программы.

## 4. Настроить проект в SignPath

После одобрения получить:

- Organization ID;
- Project slug;
- Signing policy slug;
- API token пользователя с правом отправки signing requests.

GitHub repository должен быть подключён к SignPath как trusted build system.

## 5. GitHub Secret

Repository → Settings → Secrets and variables → Actions → Secrets:

- `SIGNPATH_API_TOKEN`

## 6. GitHub Variables

Repository → Settings → Secrets and variables → Actions → Variables:

- `SIGNPATH_ORG_ID`
- `SIGNPATH_PROJECT_SLUG`
- `SIGNPATH_POLICY_SLUG`

После заполнения всех значений:

- `SIGNPATH_ENABLED` = `true`

До этого переменную `SIGNPATH_ENABLED` не создавать или оставить не равной `true`.

## 7. Запустить сборку

После настройки запустить GitHub Actions.

Ожидаемая цепочка:

`Build EXE → Upload unsigned artifact → SignPath → Verify Authenticode → SHA-256 → Release`

Если `Get-AuthenticodeSignature` не возвращает `Valid`, GitHub Release не публикуется.
