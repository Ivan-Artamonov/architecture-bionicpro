package ru.bionicpro;

import com.fasterxml.jackson.databind.JsonNode;
import org.keycloak.broker.oidc.AbstractOAuth2IdentityProvider;
import org.keycloak.broker.oidc.OAuth2IdentityProviderConfig;
import org.keycloak.broker.provider.BrokeredIdentityContext;
import org.keycloak.broker.provider.IdentityBrokerException;
import org.keycloak.broker.provider.util.SimpleHttp;
import org.keycloak.broker.social.SocialIdentityProvider;
import org.keycloak.models.KeycloakSession;
import org.keycloak.sessions.AuthenticationSessionModel;

public class YandexIdentityProvider extends AbstractOAuth2IdentityProvider<OAuth2IdentityProviderConfig>
        implements SocialIdentityProvider<OAuth2IdentityProviderConfig> {
    public YandexIdentityProvider(KeycloakSession session, OAuth2IdentityProviderConfig config) {
        super(session, config);
    }

    @Override
    protected String getDefaultScopes() {
        return "login:info login:email";
    }

    @Override
    protected BrokeredIdentityContext doGetFederatedIdentity(String accessToken) {
        try {
            SimpleHttp.Response response = SimpleHttp.doGet(getConfig().getUserInfoUrl(), session)
                    .header("Authorization", "OAuth " + accessToken).asResponse();
            if (response.getStatus() != 200) {
                throw new IdentityBrokerException("Yandex identity unavailable");
            }
            JsonNode profile = response.asJson();
            String id = getJsonProperty(profile, "id");
            if (id == null || !id.matches("[0-9]+")) {
                throw new IdentityBrokerException("Missing Yandex identity");
            }
            // Do not import names, email or other optional profile fields before application consent.
            BrokeredIdentityContext identity = new BrokeredIdentityContext(id);
            identity.setUsername("yandex." + id);
            identity.setBrokerUserId(getConfig().getAlias() + "." + id);
            return identity;
        } catch (java.io.IOException error) {
            throw new IdentityBrokerException("Yandex identity unavailable");
        }
    }

    @Override
    public void authenticationFinished(AuthenticationSessionModel authSession, BrokeredIdentityContext context) {
        super.authenticationFinished(authSession, context);
        authSession.setUserSessionNote("yandex_id", context.getId());
    }
}
