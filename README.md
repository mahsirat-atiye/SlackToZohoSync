# Backup from Slack
- Go to https://api.slack.com/apps
- Create an app
- Under `Features` go to `OAuth & Permissions`
- Add following permissions to `User Token Scopes`
  -  `channels:history`
  -  `channels:read`
  -  `groups:history`
  -  `groups:read`
  -  `im:history`
  -  `im:read`
  -  `mpim:history`
  -  `mpim:read`
  -  `users:read`

- Install the app to workspace
- Copy the `User OAuth Token` which is something like  `xoxs-123...`
- Test the token with following command
```angular2html
curl -X POST      -H 'Authorization: Bearer xoxp-123..'      -H 'Content-type: application/json;charset=utf-8'  https://slack.com/api/auth.test
```

## Setup project
```angular2html
python3 slack/slack_export.py --token xoxp-123... --publicChannels 20-30
```
### Arguments
- publicChannels: Export the given Public Channels
- groups: Export the given Private Channels / Group DMs
- directMessages: Export 1:1 DMs with the given users

### Outputs
A directory named `date-token` containing `concat.json` in each sub-directory
A file named `users.json`

# Migrate to Zoho
- Go to https://api-console.zoho.eu/
- Create a `Server-based Application`
- set both `Homepage URL` and `Authorized Redirect URIs` to https://example.com
- Complete config.yaml file
- Put `users.json` and `concat.json` in zoho directory






