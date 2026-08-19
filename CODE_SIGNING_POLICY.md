# Code signing policy

Free code signing provided by SignPath.io, certificate by SignPath Foundation.

Эта политика применяется к публичным Windows-релизам ProstoKVN Network.

## Роли

- **Committers:** [GRESHNIK2019](https://github.com/GRESHNIK2019)
- **Reviewers:** [GRESHNIK2019](https://github.com/GRESHNIK2019)
- **Approvers:** [GRESHNIK2019](https://github.com/GRESHNIK2019)

При появлении дополнительных участников список ролей должен быть обновлён до выдачи им прав на выпуск или подпись.

## Источник сборки

Подписываются только бинарные файлы ProstoKVN Network, собранные GitHub Actions из исходного кода и build-скриптов этого репозитория на GitHub-hosted runner. Локально собранные файлы не отправляются на подпись публичного релиза.

## Процесс выпуска

1. GitHub Actions проверяет исходный код и собирает `ProstoKVNNetwork.exe`.
2. Неподписанный EXE загружается как GitHub workflow artifact.
3. GitHub artifact передаётся в SignPath.
4. Подписанный EXE возвращается в workflow.
5. `Get-AuthenticodeSignature` обязан вернуть `Valid`.
6. После подписи рассчитывается SHA-256.
7. Только после этих проверок создаётся или обновляется GitHub Release.
8. Запрос подписи для публичного выпуска требует одобрения назначенного Approver в соответствии с настройками SignPath.

## Метаданные бинарного файла

Для подписываемого EXE задаются:

- Product name: `ProstoKVN Network`;
- File description: `ProstoKVN Network`;
- Original filename: `ProstoKVNNetwork.exe`;
- Company/author label: `ProstoKVN`;
- версия файла и продукта должна совпадать с версией выпуска.

## Конфиденциальность

См. [`PRIVACY.md`](PRIVACY.md). В приложении нет телеметрии или скрытой передачи данных владельцу проекта.

## Безопасность

В подписываемые артефакты не должны добавляться закрытые компоненты проекта, вредоносный код, средства скрытого сбора данных или функции обхода защитных механизмов ОС.
