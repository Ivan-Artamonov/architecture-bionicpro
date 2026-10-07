FROM curlimages/curl:8.12.1 AS fetch
WORKDIR /tmp
RUN curl -fsSL https://repo.maven.apache.org/maven2/ru/playa/keycloak/keycloak-russian-providers/23.0.6.rsp-3/keycloak-russian-providers-23.0.6.rsp-3.jar -o yandex-provider.jar && \
  curl -fsSL https://repo.maven.apache.org/maven2/com/jayway/jsonpath/json-path/2.7.0/json-path-2.7.0.jar -o json-path.jar && \
  curl -fsSL https://repo.maven.apache.org/maven2/net/minidev/json-smart/2.4.7/json-smart-2.4.7.jar -o json-smart.jar
FROM quay.io/keycloak/keycloak:23.0.6
COPY --from=fetch /tmp/yandex-provider.jar /tmp/json-path.jar /tmp/json-smart.jar /opt/keycloak/providers/
RUN /opt/keycloak/bin/kc.sh build
