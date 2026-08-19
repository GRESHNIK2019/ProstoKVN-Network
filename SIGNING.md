# Бесплатная подпись через SignPath Foundation

Для ProstoKVN Network используется бесплатная Authenticode-подпись для подходящих open-source проектов через SignPath Foundation.

Проект лицензирован по `GPL-3.0-or-later`, а публичные релизы должны собираться GitHub Actions из исходников этого репозитория.

## Перед подачей заявки

Нужно выполнить требования SignPath Foundation:

- публичный репозиторий;
- OSI-approved лицензия для собственного кода;
- отсутствие собственного proprietary-кода в подписываемом продукте;
- активная поддержка;
- опубликованный релиз;
- документированная функциональность;
- раздел `Code signing policy` на главной странице проекта;
- privacy policy;
- включённая MFA для GitHub и SignPath.

## После одобрения

В GitHub Actions добавить secret:

- `SIGNPATH_API_TOKEN`

И variables:

- `SIGNPATH_ORG_ID`
- `SIGNPATH_PROJECT_SLUG`
- `SIGNPATH_POLICY_SLUG`
- `SIGNPATH_ENABLED=true`

После этого workflow отправит GitHub workflow artifact в SignPath, дождётся подписанного EXE, проверит Authenticode и только затем опубликует Release.
