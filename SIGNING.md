# Бесплатная подпись через SignPath Foundation

Для ProstoKVN Network используем бесплатную Authenticode-подпись для open-source проектов через SignPath Foundation.

## Почему этот вариант

- Подпись предназначена для Windows Authenticode.
- Для подходящих OSS-проектов SignPath Foundation предоставляет сертификат и SignPath.io бесплатно.
- Приватный ключ хранится на стороне SignPath, а не в GitHub Secrets.
- GitHub Actions может отправлять собранный EXE на подпись автоматически.

## Важные условия SignPath Foundation

Бесплатная программа предназначена только для настоящих open-source проектов. Проект должен:

- использовать OSI-approved Open Source License;
- не содержать собственного закрытого/proprietary кода;
- быть активно поддерживаемым;
- уже иметь опубликованный релиз;
- иметь описание функциональности и страницу загрузки.

Пока лицензия не выбрана и заявка SignPath Foundation не одобрена, workflow продолжает собирать EXE как CI artifact, но не публикует его как подписанный Release.

## GitHub Secret

После одобрения SignPath добавить:

- `SIGNPATH_API_TOKEN`

## GitHub Variables

Добавить:

- `SIGNPATH_ORG_ID`
- `SIGNPATH_PROJECT_SLUG`
- `SIGNPATH_POLICY_SLUG`
- `SIGNPATH_ENABLED` = `true`

## Как работает workflow

1. PyInstaller собирает `ProstoKVNNetwork.exe`.
2. GitHub загружает неподписанный EXE как workflow artifact.
3. `signpath/github-action-submit-signing-request@v2` отправляет artifact в SignPath.
4. SignPath возвращает подписанный EXE.
5. Workflow заменяет неподписанный файл подписанным.
6. `Get-AuthenticodeSignature` обязан вернуть `Valid`.
7. Только после этого создаются SHA-256 и публичный GitHub Release.

Самоподписанные сертификаты для публичных релизов не используются.
