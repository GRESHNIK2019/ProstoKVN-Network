# Настройка цифровой подписи ProstoKVN Network

Для публичных релизов используем **Microsoft Artifact Signing** и сертификат типа **Public Trust**. Самоподписанные сертификаты для релизов не используем.

## 1. Создать Artifact Signing account

В Azure Portal:

1. Найти `Artifact Signing Accounts`.
2. Нажать `Create`.
3. Выбрать Azure subscription и resource group.
4. Создать account, например `prostokvn-signing`.
5. Выбрать поддерживаемый регион.
6. Для нашего объёма достаточно тарифа `Basic`.

После создания сохранить:

- Subscription ID
- Tenant ID
- Account name
- Endpoint региона, например `https://eus.codesigning.azure.net/`

## 2. Пройти Identity validation

Внутри Artifact Signing account:

1. Открыть `Identity validations`.
2. Создать **Public** identity validation.
3. Дождаться успешной проверки.

Важно: Public Trust для организаций доступен в США, Канаде, ЕС и Великобритании. Для индивидуальных разработчиков Microsoft сейчас указывает доступность только в США и Канаде.

## 3. Создать Certificate profile

После успешной identity validation:

1. Открыть `Certificate profiles`.
2. Создать профиль типа `Public Trust`.
3. Например: `prostokvn-public`.

Сохранить имя профиля.

## 4. Создать Microsoft Entra App Registration для GitHub Actions

Создать отдельное приложение, например `prostokvn-github-signing`.

Для него добавить Federated credential для GitHub:

- Organization: `GRESHNIK2019`
- Repository: `ProstoKVN-Network`
- Entity type: `Branch`
- Branch: `main`

После этого сохранить:

- Application (client) ID
- Directory (tenant) ID

## 5. Выдать право на подпись

На Artifact Signing account открыть `Access control (IAM)` и назначить созданному service principal роль:

`Artifact Signing Certificate Profile Signer`

## 6. Добавить GitHub Secrets

Repository → Settings → Secrets and variables → Actions → Secrets:

- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`

## 7. Добавить GitHub Variables

Repository → Settings → Secrets and variables → Actions → Variables:

- `ARTIFACT_SIGNING_ENDPOINT`
- `ARTIFACT_SIGNING_ACCOUNT`
- `ARTIFACT_SIGNING_PROFILE`

Пока всё не настроено, `ARTIFACT_SIGNING_ENABLED` не создавать или оставить не равным `true`.

После заполнения всех значений создать:

- `ARTIFACT_SIGNING_ENABLED` = `true`

## 8. Проверка

Запустить GitHub Actions вручную или сделать commit в `main`.

Ожидаемая цепочка:

`Build EXE → Validate signing config → Azure login → Artifact Signing → Verify Authenticode → SHA-256 → Release`

Публичный GitHub Release публикуется только после успешной Authenticode-подписи.
