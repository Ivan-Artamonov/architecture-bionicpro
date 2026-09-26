package ru.bionicpro;

import com.fasterxml.jackson.databind.JsonNode;
import org.keycloak.broker.oidc.AbstractOAuth2IdentityProvider;
import org.keycloak.broker.oidc.OAuth2IdentityProviderConfig;
import org.keycloak.broker.provider.BrokeredIdentityContext;
import org.keycloak.broker.provider.IdentityBrokerException;
import org.keycloak.broker.provider.util.SimpleHttp;
import org.keycloak.broker.social.SocialIdentityProvider;
import org.keycloak.models.KeycloakSession;

public class YandexProvider extends AbstractOAuth2IdentityProvider<OAuth2IdentityProviderConfig>
        implements SocialIdentityProvider<OAuth2IdentityProviderConfig> {
    public YandexProvider(KeycloakSession session, OAuth2IdentityProviderConfig config) {
        super(session, config);
        config.setAuthorizationUrl("https://oauth.yandex.ru/authorize");
        config.setTokenUrl("https://oauth.yandex.ru/token");
    }

    @Override
    protected String getDefaultScopes() { return "login:info login:email"; }

    @Override
    protected BrokeredIdentityContext doGetFederatedIdentity(String accessToken) {
        try (SimpleHttp.Response response = SimpleHttp.doGet("https://login.yandex.ru/info?format=json", session)
                .header("Authorization", "OAuth " + accessToken).asResponse()) {
            if (response.getStatus() != 200) throw new IdentityBrokerException("Yandex profile unavailable");
            JsonNode profile = response.asJson();
            String id = getJsonProperty(profile, "id");
            if (id == null || id.isBlank()) throw new IdentityBrokerException("Yandex id missing");
            BrokeredIdentityContext user = new BrokeredIdentityContext(id, getConfig());
            user.setUsername("yandex-" + id);
            user.setIdp(this);
            // Имя и email запрашиваем в приложении после согласия пользователя.
            return user;
        } catch (Exception e) {
            throw new IdentityBrokerException("Yandex login failed", e);
        }
    }
}
