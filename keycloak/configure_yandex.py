"""After filling .env with Yandex credentials: python3 keycloak/configure_yandex.py."""
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def env():
    return dict(line.split('=', 1) for line in Path('.env').read_text().splitlines()
                if line and not line.startswith('#') and '=' in line)


config = env()
if not config.get('YANDEX_CLIENT_ID') or not config.get('YANDEX_CLIENT_SECRET'):
    raise SystemExit('Fill YANDEX_CLIENT_ID and YANDEX_CLIENT_SECRET in .env')
admin_password = config.get('KEYCLOAK_ADMIN_PASSWORD', 'admin')
base = 'http://localhost:8080'
token_req = Request(base + '/realms/master/protocol/openid-connect/token',
                    data=urlencode({'client_id': 'admin-cli', 'grant_type': 'password',
                                    'username': 'admin', 'password': admin_password}).encode())
with urlopen(token_req) as response:
    token = json.load(response)['access_token']
url = base + '/admin/realms/reports-realm/identity-provider/instances'
payload = {'alias': 'yandex', 'providerId': 'yandex', 'enabled': True,
           'trustEmail': False, 'storeToken': False,
           'config': {'clientId': config['YANDEX_CLIENT_ID'],
                      'clientSecret': config['YANDEX_CLIENT_SECRET']}}
headers = {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'}
try:
    with urlopen(Request(url + '/yandex', headers=headers)):
        method, endpoint = 'PUT', url + '/yandex'
except HTTPError as error:
    if error.code != 404:
        raise
    method, endpoint = 'POST', url
req = Request(endpoint, data=json.dumps(payload).encode(), method=method,
              headers=headers)
with urlopen(req) as response:
    print('Yandex identity provider configured:', response.status)
# The reviewable export intentionally omits the live OAuth secret.
export = Path('keycloak/keycloak-results-export.json')
realm = json.loads(export.read_text())
realm['identityProviders'] = [{'alias': 'yandex', 'providerId': 'yandex',
                               'enabled': True, 'trustEmail': False,
                               'config': {'clientId': '<set in local Keycloak>',
                                          'clientSecret': '<set in local Keycloak>'}}]
export.write_text(json.dumps(realm, ensure_ascii=False, indent=2) + '\n')
