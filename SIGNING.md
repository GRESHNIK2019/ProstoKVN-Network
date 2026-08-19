# Microsoft Artifact Signing

Для публичных релизов ProstoKVN Network используется доверенная Authenticode-подпись через Microsoft Artifact Signing. Самоподписанный сертификат для релизов не используется.

## Что нужно создать в Azure

1. Artifact Signing account.
2. Certificate profile с пройденной identity validation.
3. App Registration / workload identity для GitHub Actions.
4. Для этой identity назначить роль **Artifact Signing Certificate Profile Signer**.

## GitHub Secrets

- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`

## GitHub Variables

- `ARTIFACT_SIGNING_ENABLED` = `true`
- `ARTIFACT_SIGNING_ENDPOINT`
- `ARTIFACT_SIGNING_ACCOUNT`
- `ARTIFACT_SIGNING_PROFILE`

Workflow использует `azure/login@v3` через OIDC и официальный `azure/artifact-signing-action@v2`.

После подписи workflow проверяет `Get-AuthenticodeSignature`. Только статус `Valid` разрешает публикацию GitHub Release.
