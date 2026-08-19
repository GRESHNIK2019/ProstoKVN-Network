# SignPath Foundation application checklist

## Репозиторий

- [x] Публичный GitHub-репозиторий.
- [x] Выбрана лицензия `GPL-3.0-or-later`.
- [x] README описывает функции приложения.
- [x] Есть раздел `Code signing policy`.
- [x] Есть privacy policy.
- [x] Есть инструкции удаления.
- [x] Сборка выполняется GitHub Actions на GitHub-hosted runner.
- [ ] Убедиться, что весь собственный исходный код доступен в удобном для проверки виде, а не только внутри архива релиза.
- [ ] Убедиться, что опубликован хотя бы один рабочий релиз в той форме, которую планируется подписывать.
- [ ] Включить MFA для GitHub, если ещё не включена.

## Заявка

Подать заявку SignPath Foundation для репозитория `GRESHNIK2019/ProstoKVN-Network`.

После одобрения подключить GitHub repository в SignPath как trusted build system и получить:

- Organization ID;
- Project slug;
- Signing policy slug;
- API token пользователя с правом отправки signing requests.

## GitHub

Secret:

- `SIGNPATH_API_TOKEN`

Variables:

- `SIGNPATH_ORG_ID`
- `SIGNPATH_PROJECT_SLUG`
- `SIGNPATH_POLICY_SLUG`
- `SIGNPATH_ENABLED=true`

После настройки ожидаемая цепочка:

`Build EXE → Upload unsigned artifact → SignPath → Verify Authenticode → SHA-256 → Release`
