package ru.bionicpro;

import org.keycloak.broker.oidc.OAuth2IdentityProviderConfig;
import org.keycloak.broker.provider.AbstractIdentityProviderFactory;
import org.keycloak.broker.social.SocialIdentityProviderFactory;
import org.keycloak.models.IdentityProviderModel;
import org.keycloak.models.KeycloakSession;

public class YandexProviderFactory extends AbstractIdentityProviderFactory<YandexProvider>
        implements SocialIdentityProviderFactory<YandexProvider> {
    @Override public String getName() { return "Яндекс ID"; }
    @Override public String getId() { return "yandex"; }
    @Override public OAuth2IdentityProviderConfig createConfig() { return new OAuth2IdentityProviderConfig(); }
    @Override public YandexProvider create(KeycloakSession session, IdentityProviderModel model) {
        return new YandexProvider(session, new OAuth2IdentityProviderConfig(model));
    }
}
