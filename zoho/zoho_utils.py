import json
import os
import time

from requests_oauthlib import OAuth2Session

_ZOHO_SCOPE = [
    'ZohoCliq.Attachments.READ',
    'ZohoCliq.Chats.CREATE',
    'ZohoCliq.Chats.DELETE',
    'ZohoCliq.Chats.READ',
    'ZohoCliq.Chats.UPDATE',
    'ZohoCliq.Channels.CREATE',
    'ZohoCliq.Channels.DELETE',
    'ZohoCliq.Channels.READ',
    'ZohoCliq.Channels.UPDATE',
    'ZohoCliq.Messages.DELETE',
    'ZohoCliq.Messages.READ',
    'ZohoCliq.Messages.UPDATE',
    'ZohoCliq.Users.READ',
    'ZohoCliq.Webhooks.CREATE',
    'ZohoCliq.messageactions.CREATE',
    'ZohoCliq.messageactions.DELETE'
]


def get_zoho_client(client_id, client_secret, redirect_uri,
                    token_filename='token'):
    if os.path.exists(token_filename):
        with open(token_filename) as token_file:
            token = json.loads(token_file.read())
        if 'expires_at' in token and int(token['expires_at']) > time.time():
            return OAuth2Session(client_id, token=token)

    zoho = OAuth2Session(
        client_id,
        scope=_ZOHO_SCOPE,
        redirect_uri=redirect_uri
    )
    authorization_url, state = zoho.authorization_url(
        'https://accounts.zoho.eu/oauth/v2/auth',
        access_type='offline'
    )
    print("Please go here and authorize:", authorization_url)
    redirect_response = input("Paste full redirect URL here: ")
    token = zoho.fetch_token(
        'https://accounts.zoho.eu/oauth/v2/token',
        client_secret=client_secret,
        authorization_response=redirect_response
    )

    with open('token', 'w') as token_file:
        token_file.write(json.dumps(token))
    return zoho