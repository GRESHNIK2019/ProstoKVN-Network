# Бесплатная подпись через SignPath Foundation

ProstoKVN Network готов к бесплатной Authenticode-подписи для подходящих open-source проектов через SignPath Foundation.

Проект лицензирован по `GPL-3.0-or-later`, а Windows-сборки выполняются GitHub Actions из исходников этого репозитория.

## До одобрения

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

В GitHub добавить secret:

- `SIGNPATH_API_TOKEN`

И repository variables:

- `SIGNPATH_ORG_ID`
- `SIGNPATH_PROJECT_SLUG`
- `SIGNPATH_POLICY_SLUG`
- `SIGNPATH_ENABLED=true`

После этого официальный релиз создаётся так:

1. Обновить версию в `version.json`, `src/app_config.py` и `src/version_info.txt`.
2. Проверить `python scripts/check_source.py`.
3. Создать и отправить тег, например `v0.21.0`.
4. GitHub Actions соберёт EXE и отправит release artifact в SignPath.
5. Workflow проверит `Get-AuthenticodeSignature`.
6. GitHub Release будет опубликован только при статусе подписи `Valid`.

Обычные push в `main` создают только CI artifact и не расходуют подписи SignPath.
