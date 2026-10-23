# Задание 1. Повышение безопасности системы

## Часть 1. Архитектура управления учётными данными

- [Диаграмма архитектуры draw.io](BionicPRO_C4_model.drawio.xml)
- [Диаграмма архитектуры JPG](BionicPRO_C4_model.jpg)

В каждой стране: свои BFF, Keycloak, Redis, бизнес-БД, БД Keycloak и профилей. Персональные и медицинские данные,
токены, OTP, логи и резервные копии между странами не реплицируются. Регион выбирается по домену представительства.

Keycloak подключает местный LDAP через **User Federation**, внешние IdP через **Identity Brokering**. Приложения
используют отдельные OIDC-клиенты одного регионального Keycloak.

## Часть 2. PKCE в React и Keycloak

В React включён Authorization Code + PKCE S256, в Keycloak S256 обязателен. Implicit и Direct Access Grant отключены.

