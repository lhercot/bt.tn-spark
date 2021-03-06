#!/usr/bin/env python
import json
import logging
import os
import requests
from requests_toolbelt import MultipartEncoder
import sys
import time
import yaml
from bottle import route, run, request, abort


@route("/", method=['GET', 'POST'])
def from_bttn():
    """
    Processes the press of a bt.tn device

    This function is called from far far away, over the Internet
    """

    print("Button has been pressed")

    try:

        # step 1 - get a room, or create one if needed
        #
        room_id = get_room()

        # step 2 - ensure they are some listeners here
        #
        add_audience(room_id)

        # step 3 - send a message, or upload a file, or both
        #
        update = build_update()

        # step 4 - do the actual update
        #
        post_update(room_id=room_id, update=update)

        print("Cisco Spark has been updated")
        return "OK\n"

    except Exception as feedback:
        print("ABORTED: fatal error has been encountered")
        print(str(feedback))
        return str(feedback)+'\n'


def get_room():
    """
    Looks for a suitable Cisco Spark room

    :return: the id of the target room
    :rtype: ``str``

    This function creates a new room if necessary
    """

    print("Looking for Cisco Spark room '{}'".format(settings['room']))

    url = 'https://api.ciscospark.com/v1/rooms'
    headers = {'Authorization': 'Bearer '+settings['CISCO_SPARK_BTTN_BOT']}
    response = requests.get(url=url, headers=headers)

    if response.status_code != 200:
        print(response.json())
        raise Exception("Received error code {}".format(response.status_code))

    for item in response.json()['items']:
        if settings['room'] in item['title']:
            print("- found it")
            return item['id']

    print("- not found")
    print("Creating Cisco Spark room")

    url = 'https://api.ciscospark.com/v1/rooms'
    headers = {'Authorization': 'Bearer '+settings['CISCO_SPARK_BTTN_BOT']}
    payload = {'title': settings['room'] }
    response = requests.post(url=url, headers=headers, data=payload)

    if response.status_code != 200:
        print(response.json())
        raise Exception("Received error code {}".format(response.status_code))

    print("- done")
    return response.json()['id']

def delete_room():
    """
    Deletes the target Cisco Spark room

    This function is useful to restart a clean demo environment
    """

    print("Deleting Cisco Spark room '{}'".format(settings['room']))

    url = 'https://api.ciscospark.com/v1/rooms'
    headers = {'Authorization': 'Bearer '+settings['CISCO_SPARK_BTTN_BOT']}
    response = requests.get(url=url, headers=headers)

    if response.status_code != 200:
        print(response.json())
        raise Exception("Received error code {}".format(response.status_code))

    actual = False
    for item in response.json()['items']:

        if settings['room'] in item['title']:
            print("- found it")
            print("- DELETING IT")

            url = 'https://api.ciscospark.com/v1/rooms/{}'.format(item['id'])
            headers = {'Authorization': 'Bearer '+settings['CISCO_SPARK_BTTN_BOT']}
            response = requests.delete(url=url, headers=headers)

            if response.status_code != 204:
                raise Exception("Received error code {}".format(response.status_code))

            actual = True

    if actual:
        print("- room will be re-created in Cisco Spark on next button depress")
    else:
        print("- no room with this name yet - it will be created on next button depress")

    settings['shouldAddModerator'] = True

def add_audience(room_id):
    """
    Gives a chance to some listeners to catch updates

    :param room_id: identify the target room
    :type room_id: ``str``

    This function adds pre-defined listeners to a Cisco Spark room if necessary
    """

    if settings['shouldAddModerator'] is False:
        return

    print("Adding moderator to the Cisco Spark room")

    url = 'https://api.ciscospark.com/v1/memberships'
    headers = {'Authorization': 'Bearer '+settings['CISCO_SPARK_BTTN_BOT']}
    payload = {'roomId': room_id,
               'personEmail': settings['CISCO_SPARK_BTTN_MAN'],
               'isModerator': 'true' }
    response = requests.post(url=url, headers=headers, data=payload)

    if response.status_code != 200:
        print(response.json())
        raise Exception("Received error code {}".format(response.status_code))

    print("- done")

    settings['shouldAddModerator'] = False

def build_update():
    """
    Prepares an update that can be read by human beings

    :return: the update to be posted
    :rtype: ``str`` or ``dict`

    This function monitors the number of button pushes, and uses the appropriate
    action as defined in the configuration file, under the `bt.tn:` keyword.

    The action can be either:

    * send a text message to the room with `text:` statement
    * send a Markdown message to the room with `markdown:` statement
    * upload a file with `file:`, `label:` and `type:`
    * send a message and attach a file


    """

    print("Building update")

    items = settings['bt.tn']
    if settings['count'] < len(items):
        print("- using item {}".format(settings['count']))
        item = items[ settings['count'] ]

        update = {}

        # textual message
        #
        if 'markdown' in item:

            text = 'using markdown content'
            update['markdown'] = item['markdown']

        elif 'message' in item:

            text = "'{}".format(item['message'])
            update['text'] = item['message']

        # file upload
        #
        if 'file' in item:

            print("- attaching file {}".format(item['file']))

            if 'label' in item:
                text = item['label']

                if 'text' not in update:
                    update['text'] = "'{}'".format(item['label'])

            else:
                text = item['file']

            if 'type' in item:
                type = item['type']
            else:
                type = 'application/octet-stream'

            update['files'] = (text, open(item['file'], 'rb'), type)

    else:
        text = 'ping {}'.format(settings['count'])
        update = text

    settings['count'] += 1

    print("- {}".format(text))
    return update

def post_update(room_id, update):
    """
    Updates a Cisco Spark room

    :param room_id: identify the target room
    :type room_id: ``str``

    :param update: content of the update to be posted there
    :type update: ``str`` or ``dict``

    If the update is a simple string, it is sent as such to Cisco Spark.
    Else if it a dictionary, then it is encoded as MIME Multipart.
    """

    print("Posting update to Cisco Spark room")

    url = 'https://api.ciscospark.com/v1/messages'
    headers = {'Authorization': 'Bearer '+settings['CISCO_SPARK_BTTN_BOT']}

    if isinstance(update, dict):
        update['roomId'] = room_id
        payload = MultipartEncoder(fields=update)
        headers['Content-Type'] = payload.content_type
    else:
        payload = {'roomId': room_id, 'text': update }

    response = requests.post(url=url, headers=headers, data=payload)

    if response.status_code != 200:
        print(response.json())
        raise Exception("Received error code {}".format(response.status_code))

    print('- done, check the room with Cisco Spark client software')

def configure(name="settings.yaml"):
    """
    Reads configuration information

    :param name: the file that contains configuration information
    :type name: ``str``

    The function loads configuration from the file and from the environment.
    Port number can be set from the command line.

    Sample configuration file to illustrate capabilities of the program::

        room: "Green Forge"

        CISCO_SPARK_BTTN_BOT: "YWM2OEG4OGItNTQ5YS00MDU2LThkNWEtMJNkODk3ZDZLOGQ0OVGlZWU1NmYtZWyY"
        CISCO_SPARK_BTTN_MAN: "foo.bar@acme.com"

        port: 8080

        bt.tn:

          - markdown: |
                Green Power has been invoked again
                ==================================

                The [green button](https://d2jaw3pqpetn6l.cloudfront.net/app/uploads/2016/05/27125600/product-images-bttn-normal-green-600x600.jpg) has been pressed, so there is a need for urgent action.

                Some context to this event: *Italic*, **bold**, and `monospace`.
                Itemized lists look like this:

                  * this one
                  * that one
                  * the other one

                Unicode is supported. \xe2 And [Incident Management](https://en.wikipedia.org/wiki/Incident_management_(ITSM)) too.
                Call Global Service Center at [+44 12 34 56 78](tel:+44-12-34-56-78) if people are late to join this room.
                We will continue to feed this room with information.

          - file: IncidentReportForm.pdf
            type: "application/pdf"
            label: "Print and fill this report"

          - file: bt.tn.png
            type: "image/png"
            label: "European buttons that rock"

          - file: spark.png
            type: "image/png"
            label: "Cisco Spark brings things and human beings together"

          - file: dimension-data.png
            type: "image/png"
            label: "Build new integrated systems and manage them"

    """

    print("Loading the configuration")

    with open(name, 'r') as stream:
        try:
            settings = yaml.load(stream)
            print("- from '{}'".format(name))
        except Exception as feedback:
            logging.error(str(feedback))
            sys.exit(1)

    if "room" not in settings:
        logging.error("Missing room: configuration information")
        sys.exit(1)

    if "bt.tn" not in settings:
        logging.error("Missing bt.tn: configuration information")
        sys.exit(1)

    if len(sys.argv) > 1:
        try:
            port_number = int(sys.argv[1])
        except:
            logging.error("Invalid port_number specified")
            sys.exit(1)
    elif "port" in settings:
        port_number = int(settings["port"])
    else:
        port_number = 80
    settings['port'] = port_number

    if 'DEBUG' in settings:
        debug = settings['DEBUG']
    else:
        debug = os.environ.get('DEBUG', False)
    settings['DEBUG'] = debug
    if debug:
        logging.basicConfig(level=logging.DEBUG)

    if 'CISCO_SPARK_BTTN_BOT' not in settings:
        token = os.environ.get('CISCO_SPARK_BTTN_BOT')
        if token is None:
            logging.error("Missing CISCO_SPARK_BTTN_BOT in the environment")
            sys.exit(1)
        settings['CISCO_SPARK_BTTN_BOT'] = token

    if 'CISCO_SPARK_BTTN_MAN' not in settings:
        emails = os.environ.get('CISCO_SPARK_BTTN_MAN')
        if emails is None:
            logging.error("Missing CISCO_SPARK_NTTN_MAN in the environment")
            sys.exit(1)
        settings['CISCO_SPARK_BTTN_MAN'] = emails

    settings['count'] = 0

    return settings

# the program launched from the command line
#
if __name__ == "__main__":

    # read configuration file, look at the environment
    #
    settings = configure()

    # create a clean environment for the demo
    #
    delete_room()

    # wait for button pushes and process them
    #
    print("Preparing for web requests")
    run(host='0.0.0.0',
        port=settings['port'],
        debug=settings['DEBUG'],
        server=os.environ.get('SERVER', "auto"))
