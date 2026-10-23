# Задание 1. Повышение безопасности системы

## Часть 1. Архитектура управления учётными данными

- [Диаграмма архитектуры draw.io](BionicPRO_C4_model.drawio.xml)
- [Диаграмма архитектуры JPG](BionicPRO_C4_model.jpg)

В каждой стране: свои BFF, Keycloak, Redis, бизнес-БД, БД Keycloak и профилей. Персональные и медицинские данные,
токены, OTP, логи и резервные копии между странами не реплицируются. Регион выбирается по домену представительства.

Keycloak подключает местный LDAP через **User Federation**, внешние IdP через **Identity Brokering**. Приложения
используют отдельные OIDC-клиенты одного регионального Keycloak.

## Часть 2. PKCE в React и Keycloak

PKCE S256 обязателен в Keycloak; после части 3 обработка code/verifier перенесена из React в BFF.
Implicit и Direct Access Grant отключены.

## Часть 3. Серверные токены и сессии

`bionicpro-auth` получает и обновляет токены через Keycloak. Access token и refresh token хранятся в Redis в памяти.
React работает только с HttpOnly-cookie (`credentials: 'include'`).
При каждом защищённом запросе сервис перепривязывает токены к новому session ID и обновляет cookie, сразу инвалидируя старый ID, даже если access token ещё действителен.

**Запуск:**

- Cоздайте `.env` по `.env.example` (`chmod 600 .env`): secret `openssl rand -hex 32`, ключ
  `openssl rand -base64 32`.
- Запустите `docker compose up -d --build` → `http://localhost:3000`.
- Настройки существующего realm примените вручную из `keycloak/realm-export.json`.

## Часть 4. LDAP и роли представительства

OpenLDAP разворачивается через [Compose](../../docker-compose.yaml), пользователи и группы в [LDIF](../../ldap/config.ldif).

Keycloak проверяет пароли в LDAP и сопоставляет группы с ролями: `jane.smith` → `user`,
`john.doe` и `alex.johnson` → `prothetic_user`. Тестовый пароль — `password`. Доступ к LDAP — только на чтение.

**Запуск:** заполните три LDAP-пароля в `.env` по `.env.example` (`openssl rand -hex 32` для каждого),
затем `docker compose up -d --build`. Для существующего realm добавьте LDAP-провайдер и маппер ролей
из `components` в `keycloak/realm-export.json`, выполните **Sync all users**.

LDAP и Keycloak размещаются в одной стране, пользовательские данные между странами не реплицируются.

## Часть 5. MFA

В Keycloak включён обязательный OTP для всех пользователей, включая LDAP: TOTP, 6 цифр, период 30 секунд.
При первом входе отсканируйте QR-код в Google Authenticator или FreeOTP и подтвердите настройку кодом;
при следующих входах после пароля требуется одноразовый код. Действующая SSO-сессия повторного ввода не требует.

