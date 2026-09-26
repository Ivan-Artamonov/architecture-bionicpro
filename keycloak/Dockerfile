FROM maven:3.9.9-eclipse-temurin-21 AS build
WORKDIR /src
COPY yandex-provider/ .
RUN mvn -q package -DskipTests
FROM quay.io/keycloak/keycloak:26.3.3
COPY --from=build /src/target/yandex-provider-1.0.jar /opt/keycloak/providers/
