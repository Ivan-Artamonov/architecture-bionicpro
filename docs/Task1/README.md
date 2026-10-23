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
