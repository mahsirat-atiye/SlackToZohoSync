from slack_sdk import WebClient
import json
import argparse
import os
import io
import shutil
import copy
from datetime import datetime
from pick import pick
from time import sleep
import glob
import http
import urllib
import sys
import emoji

chat_place_holder = """<li class="chat-right">
                                    <div class="chat-hour"> chattime </div>
                                    <div class="chat-text"> chattext <div class="chat-avatar">
                                <div class="chat-name"> chatsender </div>
                            </div>
                        </li>
                    """


# fetches the complete message history for a channel/group/im
#
# pageableObject could be:
# slack.channel
# slack.groups
# slack.im
#
# channelId is the id of the channel/group/im you want to download history for.
def getHistory(client, channelId, pageSize=500):
    messages = []
    lastTimestamp = None

    response = slack.conversations_history(
        channel=channelId,
        latest=lastTimestamp,
        oldest=0,
        limit=pageSize
    )
    messages = response['messages']
    while response['has_more'] == True:
        response = slack.conversations_history(
            cursor=response['response_metadata']['next_cursor'],
            channel=channelId,
            latest=lastTimestamp,
            oldest=0,
            limit=pageSize
        )
        messages.extend(response['messages'])
        sleep(1)

    messages.sort(key=lambda message: message['ts'])

    return messages


def mkdir(directory):
    if not os.path.isdir(directory):
        os.makedirs(directory)


# create datetime object from slack timestamp ('ts') string
def parseTimeStamp(timeStamp):
    if '.' in timeStamp:
        t_list = timeStamp.split('.')
        if len(t_list) != 2:
            raise ValueError('Invalid time stamp')
        else:
            return datetime.utcfromtimestamp(float(t_list[0]))


# move channel files from old directory to one with new channel name
def channelRename(oldRoomName, newRoomName):
    # check if any files need to be moved
    if not os.path.isdir(oldRoomName):
        return
    mkdir(newRoomName)
    for fileName in os.listdir(oldRoomName):
        shutil.move(os.path.join(oldRoomName, fileName), newRoomName)
    os.rmdir(oldRoomName)


def writeMessageFile(fileName, messages):
    directory = os.path.dirname(fileName)

    # if there's no data to write to the file, return
    if not messages:
        return

    if not os.path.isdir(directory):
        mkdir(directory)

    with open(fileName, 'w') as outFile:
        json.dump(messages, outFile, indent=4, ensure_ascii=False)


# parse messages by date
def parseMessages(roomDir, messages, roomType):
    nameChangeFlag = roomType + "_name"

    currentFileDate = ''
    currentMessages = []
    for message in messages:
        # first store the date of the next message
        ts = parseTimeStamp(message['ts'])
        fileDate = '{:%Y-%m-%d}'.format(ts)

        # if it's on a different day, write out the previous day's messages
        if fileDate != currentFileDate:
            outFileName = u'{room}/{file}.json'.format(room=roomDir, file=currentFileDate)
            writeMessageFile(outFileName, currentMessages)
            currentFileDate = fileDate
            currentMessages = []

        # check if current message is a name change
        # dms won't have name change events
        if roomType != "im" and ('subtype' in message) and message['subtype'] == nameChangeFlag:
            roomDir = message['name']
            oldRoomPath = message['old_name']
            newRoomPath = roomDir
            channelRename(oldRoomPath, newRoomPath)

        currentMessages.append(message)
    outFileName = u'{room}/{file}.json'.format(room=roomDir, file=currentFileDate)
    writeMessageFile(outFileName, currentMessages)


def filterConversationsByName(channelsOrGroups, channelOrGroupNames):
    return [conversation for conversation in channelsOrGroups if conversation['name'] in channelOrGroupNames]


def promptForPublicChannels(channels):
    channelNames = [channel['name'] for channel in channels]
    selectedChannels = pick(channelNames, 'Select the Public Channels you want to export:', multi_select=True)
    return [channels[index] for channelName, index in selectedChannels]


# fetch and write history for all public channels
def fetchPublicChannels(channels):
    if dryRun:
        print("Public Channels selected for export:")
        for channel in channels:
            print(channel['name'])
        print()
        return

    for channel in channels:
        end = 0
        fails = 0
        counter = 0
        history_flag = False
        channelDir = channel['name']  # .encode('utf-8')
        print(u"Fetching history for Public Channel: {0}".format(channelDir))
        channelDir = channel['name']  # .encode('utf-8')
        while end == 0:
            try:
                if history_flag == False:
                    mkdir(channelDir)
                    messages = getHistory(slack, channel['id'])
                while counter < len(messages):
                    if 'thread_ts' in messages[counter]:
                        replies = getThread(channel['id'], messages[counter]['thread_ts'])
                        replies.sort(key=lambda replies: replies['ts'])
                        messages[counter]['replies'] = replies[1:]
                        sleep(1)
                    counter += 1
                    if counter % 200 == 0:
                        print("Checked 200 messages. Only " + str(len(messages) - counter) + " messages left!")
                # messages = slack.conversations_history(channel=channel['id'])
                parseMessages(channelDir, messages, 'channel')
                end = 1
            except urllib.error.URLError:
                fails += 1
                if (fails == 6):
                    sys.exit("too many failed attempts. Maybe check internet connection.")
                print("Retrying...")
                sleep(fails ** fails)


# write channels.json file
def dumpChannelFile():
    print("Making channels file")

    private = []
    mpim = []

    for group in groups:
        if group['is_mpim']:
            mpim.append(group)
            continue
        private.append(group)

    # slack viewer wants DMs to have a members list, not sure why but doing as they expect
    for dm in dms:
        dm['members'] = [dm['user'], tokenOwnerId]

    # We will be overwriting this file on each run.
    with open('channels.json', 'w') as outFile:
        json.dump(channels, outFile, indent=4, ensure_ascii=False)
    with open('groups.json', 'w') as outFile:
        json.dump(private, outFile, indent=4, ensure_ascii=False)
    with open('mpims.json', 'w') as outFile:
        json.dump(mpim, outFile, indent=4, ensure_ascii=False)
    with open('dms.json', 'w') as outFile:
        json.dump(dms, outFile, indent=4, ensure_ascii=False)


def filterDirectMessagesByUserNameOrId(dms, userNamesOrIds):
    userIds = [userIdsByName.get(userNameOrId, userNameOrId) for userNameOrId in userNamesOrIds]
    return [dm for dm in dms if dm['user'] in userIds]


def promptForDirectMessages(dms):
    dmNames = [userNamesById.get(dm['user'], dm['user'] + " (name unknown)") for dm in dms]
    selectedDms = pick(dmNames, 'Select the 1:1 DMs you want to export:', multi_select=True)
    return [dms[index] for dmName, index in selectedDms]


# fetch and write history for all direct message conversations
# also known as IMs in the slack API.
def fetchDirectMessages(dms):
    if dryRun:
        print("1:1 DMs selected for export:")
        for dm in dms:
            print(userNamesById.get(dm['user'], dm['user'] + " (name unknown)"))
        print()
        return

    for dm in dms:
        end = 0
        fails = 0
        name = userNamesById.get(dm['user'], dm['user'] + " (name unknown)")
        counter = 0
        history_flag = False
        dmId = dm['id']
        print(u"Fetching 1:1 DMs with {0}".format(name))
        while end == 0:
            try:
                if history_flag == False:
                    mkdir(dmId)
                    messages = getHistory(slack, dm['id'])
                    history_flag = True
                print("Fetching threads")
                print("Checking " + str(len(messages)) + " messages!")
                while counter < len(messages):
                    if 'thread_ts' in messages[counter]:
                        replies = getThread(dm['id'], messages[counter]['thread_ts'])
                        replies.sort(key=lambda replies: replies['ts'])
                        messages[counter]['replies'] = replies[1:]
                        sleep(1)
                    counter += 1
                    if counter % 200 == 0:
                        print("Checked 200 messages. Only " + str(len(messages) - counter) + " messages left!")
                # messages = slack.conversations_history(channel=dm['id'])
                parseMessages(dmId, messages, "im")
                end = 1
            except urllib.error.URLError:
                fails += 1
                if (fails == 6):
                    sys.exit("too many failed attempts. Maybe check internet connection.")
                print("Retrying...")
                sleep(fails ** fails)


def promptForGroups(groups):
    groupNames = [group['name'] for group in groups]
    selectedGroups = pick(groupNames, 'Select the Private Channels and Group DMs you want to export:',
                          multi_select=True)
    return [groups[index] for groupName, index in selectedGroups]


def getThread(channelId, ts, pageSize=500):
    messages = []
    lastTimestamp = None
    response = slack.conversations_replies(
        channel=channelId,
        ts=ts,
        latest=lastTimestamp,
        oldest=0,
        limit=pageSize
    )
    messages = response['messages']
    while response['has_more'] == True:
        response = slack.conversations_replies(
            cursor=response['response_metadata']['next_cursor'],
            channel=channelId,
            ts=ts,
            latest=lastTimestamp,
            oldest=0,
            limit=pageSize
        )
        messages.extend(response['messages'])
        sleep(1)
    messages.sort(key=lambda message: message['ts'])

    return messages


# fetch and write history for specific private channel
# also known as groups in the slack API.
def fetchGroups(groups):
    if dryRun:
        print("Private Channels and Group DMs selected for export:")
        for group in groups:
            print(group['name'])
        print()
        return

    for group in groups:
        end = 0
        fails = 0
        history_flag = False
        counter = 0
        messages = []
        groupDir = group['name']
        print(u"Fetching history for Private Channel / Group DM: {0}".format(group['name']))
        while end == 0:
            try:
                if (history_flag == False):
                    mkdir(groupDir)
                    messages = getHistory(slack, group['id'])
                    history_flag = True
                print("Fetching threads")
                print("Checking " + str(len(messages)) + " messages!")
                while counter < len(messages):
                    if 'thread_ts' in messages[counter]:
                        replies = getThread(group['id'], messages[counter]['thread_ts'])
                        replies.sort(key=lambda replies: replies['ts'])
                        messages[counter]['replies'] = replies[1:]
                        sleep(1)
                    counter += 1
                    if counter % 200 == 0:
                        print("Checked 200 messages. Only " + str(len(messages) - counter) + " messages left!")

                # messages = slack.conversations_history(channel=group['id'])
                parseMessages(groupDir, messages, 'group')
                end = 1
            except urllib.error.URLError:
                fails += 1
                if (fails == 6):
                    sys.exit("too many failed attempts. Maybe check internet connection.")
                print("Retrying...")
                sleep(fails ** fails)


# fetch all users for the channel and return a map userId -> userName
def getUserMap():
    global userNamesById, userIdsByName
    for user in users:
        userNamesById[user['id']] = user['name']
        userIdsByName[user['name']] = user['id']


# stores json of user info
def dumpUserFile():
    # write to user file, any existing file needs to be overwritten.
    with open("users.json", 'w') as userFile:
        json.dump(users, userFile, indent=4, ensure_ascii=False)


# get basic info about the slack channel to ensure the authentication token works
def doTestAuth():
    testAuth = slack.api_test()
    if testAuth['ok'] == True:
        teamName = testAuth['team']
        currentUser = testAuth['user']
        print(u"Successfully authenticated for team {0} and user {1} ".format(teamName, currentUser))
        return testAuth
    else:
        exit(testAuth['error'])


# Since Slacker does not Cache.. populate some reused lists
def bootstrapKeyValues():
    global users, channels, groups, dms
    data = slack.users_list()
    users.extend(data['members'])
    while data['response_metadata']['next_cursor']:
        data = slack.users_list(cursor=data['response_metadata']['next_cursor'])
        users.extend(data['members'])
        sleep(1)

    print(u"Found {0} Users".format(len(users)))
    sleep(1)

    data = slack.conversations_list(types="public_channel")
    channels.extend(data['channels'])
    while data['response_metadata']['next_cursor']:
        data = slack.conversations_list(types="public_channel", cursor=data['response_metadata']['next_cursor'])
        channels.extend(data['channels'])
        sleep(1)

    print(u"Found {0} Public Channels".format(len(channels)))
    sleep(1)

    data = slack.conversations_list(types="private_channel,mpim")
    groups.extend(data['channels'])
    while data['response_metadata']['next_cursor']:
        data = slack.conversations_list(types="private_channel,mpim", cursor=data['response_metadata']['next_cursor'])
        groups.extend(data['channels'])
        sleep(1)

    print(u"Found {0} Private Channels or Group DMs".format(len(groups)))
    sleep(1)

    data = slack.conversations_list(types="im")
    dms.extend(data['channels'])
    while data['response_metadata']['next_cursor']:
        data = slack.conversations_list(types="im", cursor=data['response_metadata']['next_cursor'])
        dms.extend(data['channels'])
        sleep(1)

    print(u"Found {0} 1:1 DM conversations\n".format(len(dms)))
    sleep(1)

    getUserMap()


# Returns the conversations to download based on the command-line arguments
def selectConversations(allConversations, commandLineArg, filter, prompt):
    global args
    if isinstance(commandLineArg, list) and len(commandLineArg) > 0:
        return filter(allConversations, commandLineArg)
    elif commandLineArg != None or not anyConversationsSpecified():
        if args.prompt:
            return prompt(allConversations)
        else:
            return allConversations
    else:
        return []


# Returns true if any conversations were specified on the command line
def anyConversationsSpecified():
    global args
    return args.publicChannels != None or args.groups != None or args.directMessages != None


# This method is used in order to create a empty Channel if you do not export public channels
# otherwise, the viewer will error and not show the root screen. Rather than forking the editor, I work with it.
def dumpDummyChannel():
    channelName = channels[0]['name']
    mkdir(channelName)
    fileDate = '{:%Y-%m-%d}'.format(datetime.today())
    outFileName = u'{room}/{file}.json'.format(room=channelName, file=fileDate)
    writeMessageFile(outFileName, [])


def finalize():
    print("Finalized called"*9)
    global chat_place_holder
    chatplace = chat_place_holder
    chats = ""
    users = {}
    with open('../users.json') as users_json:
        data = json.load(users_json)
        for user in data:
            profile = user['profile']
            users[user['id']] = profile['real_name']

    dirnames = {}
    htmlreader = open('../chat_template.html')
    htmltemplate = htmlreader.read()
    htmlreader.close()
    for root, dirs, files in os.walk('./', topdown=False):
        for name in dirs:
            user_names = []
            concatfilename = './' + name + '/concat.json'
            with open(concatfilename, 'wb') as outfile:
                for filename in sorted(glob.glob('./' + name + '/*.json')):
                    if filename == concatfilename:
                        continue
                    with open(filename, 'rb') as readfile:
                        shutil.copyfileobj(readfile, outfile)
            print(f"Parsing {name}...")
            outputfilename = './' + name + '/out.txt'
            outputhtmlpath = './' + name + '/out.html'
            reader = open(concatfilename, 'r')
            data = reader.read().replace('][', ',')
            reader.close()
            reader = open(concatfilename, 'w')
            reader.write(data)
            reader.close()
            with open(concatfilename) as data_json, open(outputfilename, 'w') as output:
                data_json = data_json.read()
                if len(data_json) == 0:
                    continue
                data = json.loads(data_json)
                for message in data:
                    try:
                        text = message['text']
                        try:
                            for file in message['files']:
                                text += "\n" + file['url_private_download']
                        except KeyError:
                            pass
                        output.write(datetime.fromtimestamp(int(float(message['ts']))).strftime(
                            "%a, %d %b %Y %H:%M:%S") + '   ' + users[message['user']] + ": " + text + '\n\r')
                        chatplace = chatplace.replace('chattime',
                                                      datetime.fromtimestamp(int(float(message['ts']))).strftime(
                                                          "%a, %d %b %Y %H:%M:%S")).replace('chattext',
                                                                                            emoji.emojize(text,
                                                                                                          use_aliases=True)).replace(
                            'chatsender', users[message['user']])
                        chats += chatplace
                        chatplace = chat_place_holder
                        if 'replies' in message:
                            for reply in message['replies']:
                                rep_text = reply['text']
                                try:
                                    for file in reply['files']:
                                        rep_text += "\n" + file['url_private_download']
                                except KeyError:
                                    pass
                                output.write('        ' + datetime.fromtimestamp(int(float(reply['ts']))).strftime(
                                    "%a, %d %b %Y %H:%M:%S") + '   ' + users[reply['user']] + ": " + rep_text + '\n\r')
                                chatplace = chatplace.replace('chattime',
                                                              datetime.fromtimestamp(int(float(reply['ts']))).strftime(
                                                                  "%a, %d %b %Y %H:%M:%S")).replace('chattext',
                                                                                                    emoji.emojize(
                                                                                                        rep_text,
                                                                                                        use_aliases=True)).replace(
                                    'chatsender', users[reply['user']])
                                chats += chatplace
                                chatplace = chat_place_holder
                        user_names.append(users[message['user']])
                        user_names = list(dict.fromkeys(user_names))
                    except KeyError:
                        output.write(datetime.fromtimestamp(int(float(message['ts']))).strftime(
                            "%a, %d %b %Y %H:%M:%S") + '   ' + ": " + text + '\n\r')
                        chatplace = chatplace.replace('chattime',
                                                      datetime.fromtimestamp(int(float(message['ts']))).strftime(
                                                          "%a, %d %b %Y %H:%M:%S")).replace('chattext',
                                                                                            emoji.emojize(text,
                                                                                                          use_aliases=True))
                        chats += chatplace
                        chatplace = chat_place_holder
                        if 'replies' in message:
                            for reply in message['replies']:
                                rep_text = reply['text']
                                try:
                                    for file in reply['files']:
                                        rep_text += "\n" + file['url_private_download']
                                except KeyError:
                                    pass
                                output.write('        ' + datetime.fromtimestamp(int(float(reply['ts']))).strftime(
                                    "%a, %d %b %Y %H:%M:%S") + '   ' + ": " + rep_text + '\n\r')
                                chatplace = chatplace.replace('chattime',
                                                              datetime.fromtimestamp(int(float(reply['ts']))).strftime(
                                                                  "%a, %d %b %Y %H:%M:%S")).replace('chattext',
                                                                                                    emoji.emojize(
                                                                                                        rep_text,
                                                                                                        use_aliases=True))
                                chats += chatplace
                                chatplace = chat_place_holder
            if (len(user_names) == 2):
                dirnames['./' + name] = f'./{user_names[0]}-{user_names[1]}'
                print(name + '     ' + user_names[0] + user_names[1])
            reader = open(outputhtmlpath, 'w')
            reader.write(htmltemplate.replace('chatplaceholder', chats))
    print("Done!")
    # for key in dirnames:
    #     print(key + '     ' + dirnames[key])
    #     os.rename(key, dirnames[key])
    os.chdir('..')
    if zipName:
        shutil.make_archive(zipName, 'zip', outputDirectory, None)
        shutil.rmtree(outputDirectory)
    exit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Export Slack history')

    parser.add_argument('--token', required=True, help="Slack API token")
    parser.add_argument('--zip', help="Name of a zip file to output as")

    parser.add_argument(
        '--dryRun',
        action='store_true',
        default=False,
        help="List the conversations that will be exported (don't fetch/write history)")

    parser.add_argument(
        '--publicChannels',
        nargs='*',
        default=None,
        metavar='CHANNEL_NAME',
        help="Export the given Public Channels")

    parser.add_argument(
        '--groups',
        nargs='*',
        default=None,
        metavar='GROUP_NAME',
        help="Export the given Private Channels / Group DMs")

    parser.add_argument(
        '--directMessages',
        nargs='*',
        default=None,
        metavar='USER_NAME',
        help="Export 1:1 DMs with the given users")

    parser.add_argument(
        '--prompt',
        action='store_true',
        default=False,
        help="Prompt you to select the conversations to export")

    args = parser.parse_args()

    users = []
    channels = []
    groups = []
    dms = []
    userNamesById = {}
    userIdsByName = {}

    slack = WebClient(token=args.token)
    testAuth = doTestAuth()
    tokenOwnerId = testAuth['user_id']

    try:
        u = open("users.json")
        c = open("channels.json")
        d = open("dms.json")
        g = open("groups.json")
        m = open("mpims.json")
        u_data = json.loads(u.read())
        c_data = json.loads(c.read())
        d_data = json.loads(d.read())
        g_data = json.loads(g.read())
        m_data = json.loads(m.read())
        for user in u_data:
            users.append(user)
        for ch in c_data:
            channels.append(ch)
        for dm in d_data:
            dms.append(dm)
        for gp in g_data:
            groups.append(gp)
        for mp in m_data:
            groups.append(user)
        u.close()
        c.close()
        d.close()
        g.close()
        m.close()
    except FileNotFoundError:
        print("Fetching data from server.")
        end = 0
        fails = 0
        while end == 0:
            try:
                bootstrapKeyValues()
                end = 1
            except http.client.IncompleteRead:
                fails += 1
                print("Retrying...")
                if (fails == 6):
                    sys.exit("Too many failed attempts. Maybe check internet connection.")
                sleep(fails ** fails)
        dumpUserFile()
        dumpChannelFile()

    dryRun = args.dryRun
    zipName = args.zip

    outputDirectory = "{date}-{token}-slack_export".format(token=args.token,
                                                           date=datetime.now().strftime("%Y-%m-%d-%H-%M-%S"))
    mkdir(outputDirectory)
    os.chdir(outputDirectory)

    selectedChannels = selectConversations(
        channels,
        args.publicChannels,
        filterConversationsByName,
        promptForPublicChannels)

    selectedGroups = selectConversations(
        groups,
        args.groups,
        filterConversationsByName,
        promptForGroups)

    selectedDms = selectConversations(
        dms,
        args.directMessages,
        filterDirectMessagesByUserNameOrId,
        promptForDirectMessages)

    if len(selectedChannels) > 0:
        fetchPublicChannels(selectedChannels)

    if len(selectedGroups) > 0:
        if len(selectedChannels) == 0:
            dumpDummyChannel()
        fetchGroups(selectedGroups)

    if len(selectedDms) > 0:
        fetchDirectMessages(selectedDms)

    finalize()