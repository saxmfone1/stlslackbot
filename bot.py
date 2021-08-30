import logging
import os
from tempfile import TemporaryDirectory

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
import requests

from lib.openscad import generate_png
from lib.thingiverse import ThingiverseClient, ThingInvalidThingException

log = logging.getLogger('bot')
log.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
log.addHandler(ch)


class MissingTokenException(Exception):
    pass


try:
    SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
except KeyError:
    log.error("No slack bot token provided")
    raise MissingTokenException("No slack bot token was provided in the env. Please set SLACK_BOT_TOKEN.")

try:
    SLACK_APP_TOKEN = os.environ["SLACK_APP_TOKEN"]
except KeyError:
    log.error("No slack app token provided")
    raise MissingTokenException("No slack app token was provided in the env. Please set SLACK_APP_TOKEN.")

try:
    THINGIVERSE_TOKEN = os.environ["THINGIVERSE_TOKEN"]
except KeyError:
    log.error("No thingiverse token provided")
    raise MissingTokenException("No thingiverse token was provided in the env. Please set THINGIVERSE_TOKEN.")


def get_pngs_from_thingiverse(tempdir, thing):
    log.debug(f"Trying to pull down thingid: {thing} and store it in {tempdir}")
    pngs = []
    stls = thing_client.get_stls(thing)
    files = thing_client.download_stls(tempdir, stls)
    for file in files:
        log.debug(f"found stl: {file}")
        png = generate_png(tempdir, file)
        pngs.append(png)
    return pngs


def get_pngs_from_attachment(tempdir, stls):
    log.debug(f"Trying to pull down attachment: {stls} and store it in {tempdir}")
    pngs = []
    for file in stls:
        log.debug(f"found stl: {file}")
        png = generate_png(tempdir, file)
        pngs.append(png)
    return pngs


app = App(token=SLACK_BOT_TOKEN)
thing_client = ThingiverseClient(THINGIVERSE_TOKEN)
log.debug("Setting up thingiverse api")


@app.command("/thing")
def show_thing(ack, respond, command):
    ack()
    thing = command['text']
    if thing == "":
        log.debug("!thing called with no arguments")
        respond("you forgot to post a thing!")
    else:
        log.info(f"!thing called for {thing}")
        respond(f"@{command['user'] asked for thing: {thing}} ")
        with TemporaryDirectory() as tempdir:
            log.debug(f"created tempdir: {tempdir}")
            try:
                pngs = get_pngs_from_thingiverse(tempdir, thing)
            except ThingInvalidThingException:
                respond("this is not a valid thing!")
            if len(pngs) > 0:
                for png in pngs:
                    log.debug(f"sending {png} to ")
                    app.client.files_upload(file=png, channels=command['channel_id'])
                    log.debug(f"{png} sent")
            else:
                respond("there were no stls found on this thing")


@app.event("message")
def handle_message_events(body):
    if len(body['event']['files']) > 0:
        channel_id = body['event']['channel']
        stls = []
        with TemporaryDirectory() as tempdir:
            log.debug(f"created tempdir: {tempdir}")
            for file in body['event']['files']:
                if file['filetype'] == 'binary' and file['name'].lower().endswith('.stl'):
                    log.info(f"found stl in attachment {file['name']}")
                    thing = f"{os.path.basename(file['name'])}"
                    log.debug(f"saving attachment to {tempdir}/{thing}")
                    response = requests.get(file['url_private_download'], headers={"Authorization": f"Bearer {app.client.token}"})
                    with open(f'{tempdir}/{thing}', 'wb') as f:
                        f.write(response.content)
                    stls.append(f"{tempdir}/{thing}")
            if len(stls) > 0:
                pngs = get_pngs_from_attachment(tempdir, stls)
                for png in pngs:
                    log.debug(f"sending {png} to ")
                    app.client.files_upload(file=png, channels=channel_id)
                    log.debug(f"{png} sent")
            else:
                log.info("No stls were attached")


if __name__ == '__main__':
    SocketModeHandler(app, SLACK_APP_TOKEN).start()
