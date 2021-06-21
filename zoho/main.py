from datetime import datetime
from time import sleep

import yaml
import json
import emoji

from utils import pretty_print
from zoho_utils import get_zoho_client

CONFIG_FILE = "config.yaml"
watchdog = 2


def main():
    print("1. Send messages to Channel")
    print("2. Send mesages to User")
    inp = input()
    if inp == "1":
        print("Choose number from existing channels:")
        TYPE = "channels"
    elif inp == "2":
        print("Enter email address of the user:")
        email = input()
        TYPE = "buddies"
    else:
        exit("Wrong choice!")

    users = {}
    with open('users.json') as users_json:
        data = json.load(users_json)
        for user in data:
            profile = user['profile']
            users[user['id']] = profile['real_name']

    with open(CONFIG_FILE) as config_file:
        config = yaml.load(config_file, Loader=yaml.FullLoader)

    zoho = get_zoho_client(
        config['zoho']['client_id'],
        config['zoho']['client_secret'],
        config['redirect_uri']
    )

    if TYPE == "channels":
        response = zoho.get('https://accounts.zoho.eu/oauth/v2/auth')
        response = zoho.get('https://cliq.zoho.eu/api/v2/channels')
        print(response.content)

        channels = response.json()['channels']

        channel_names = [channel['name'] for channel in channels]
        for i in range(len(channel_names)):
            print(str(i + 1) + ": " + channel_names[i])
        print("Enter number of the channel to post messages to:")
        inp = int(input()) - 1

        channel_id = [channel for channel in channels if channel['name'] == channel_names[inp]][0]['channel_id']
        print(channel_id)
    else:
        channel_id = email

    concatfilename = './concat.json'
    reader = open(concatfilename, 'r')
    data = reader.read().replace('][', ',')
    reader.close()
    reader = open(concatfilename, 'w')
    reader.write(data)
    reader.close()
    with open(concatfilename) as data_json:
        data_json = data_json.read()
        if len(data_json) == 0:
            exit()
        data = json.loads(data_json)
        for message in data:
            try:
                text = emoji.emojize(message['text'], use_aliases=True)
                try:
                    for file in message['files']:
                        text += "\n" + file['url_private_download']
                except KeyError:
                    pass
                try:
                    writer = users[message['user']]
                except:
                    writer = "Some one: " + message['user']
                post_to_zoho(zoho, TYPE, channel_id, {
                    'text': datetime.fromtimestamp(int(float(message['ts']))).strftime(
                        "%a, %d %b %Y %H:%M:%S") + '   ' + writer + ": " + text + '\n\r'})
                if 'replies' in message:
                    for reply in message['replies']:
                        rep_text = emoji.emojize(reply['text'], use_aliases=True)
                        try:
                            for file in reply['files']:
                                rep_text += "\n" + file['url_private_download']
                        except KeyError:
                            pass
                        try:
                            replyerr = users[reply['user']]
                        except:
                            replyerr = "Some one: " + reply['user']
                        post_to_zoho(zoho, TYPE, channel_id,
                                     {'text': '===>   ' + replyerr + ": " + rep_text + '\n\r'})
            except KeyError:
                post_to_zoho(zoho, TYPE, channel_id, {
                    'text': datetime.fromtimestamp(int(float(message['ts']))).strftime(
                        "%a, %d %b %Y %H:%M:%S") + '   Unknown User' + ": " + text + '\n\r'})
                if 'replies' in message:
                    for reply in message['replies']:
                        rep_text = emoji.emojize(reply['text'], use_aliases=True)
                        try:
                            for file in reply['files']:
                                rep_text += "\n" + file['url_private_download']
                        except KeyError:
                            pass
                        try:
                            replyer = users[reply['user']]
                        except:
                            replyer = "Some One:" + reply['user']
                        post_to_zoho(zoho, TYPE, channel_id,
                                     {'text': '===>   ' + replyer + ": " + rep_text + '\n\r'})

            post_to_zoho(zoho, TYPE, channel_id, {'text': '---'})
    print("Done!")


def post_to_zoho(zoho, type, channel_id, message):
    print("message is: ", message)
    global watchdog
    response = zoho.post('https://cliq.zoho.eu/api/v2/' + type + '/%s/message' % channel_id, json=message)
    if (response.status_code != 204):
        if watchdog == 0:
            exit("There is a problem!")
        print(response.status_code)
        print(response.content)
        print("API Limit Exceeded or Internet Problem. Retrying in 10s.")
        sleep(10)
        watchdog -= 1
        post_to_zoho(zoho, type, channel_id, message)
    elif response.status_code == 204:
        watchdog = 2
    sleep(1)


if __name__ == '__main__':
    main()
