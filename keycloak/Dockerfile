FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /build
COPY yandex-provider/pom.xml .
COPY yandex-provider/src ./src
RUN --mount=type=cache,target=/root/.m2 mvn -q -DskipTests package

FROM quay.io/keycloak/keycloak:21.1.2
COPY --from=build /build/target/yandex-provider-1.0.0.jar /opt/keycloak/providers/yandex-provider.jar
