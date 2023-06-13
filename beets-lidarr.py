import json
import logging
from logging.handlers import RotatingFileHandler
import os
import re
import subprocess
import requests


def parse_response(response):
    try:
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logging.error(e)
    return None


# %% Log messages to a file
# logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.basicConfig(handlers=[RotatingFileHandler('/config/logs/auto-beets.txt', maxBytes=1000000, backupCount=5)],
                    encoding='utf-8',
                    format='%(asctime)s %(levelname)-8s %(message)s',
                    datefmt='%Y-%m-%d,%H:%M:%S',
                    level=logging.INFO
                    )

# %% Lidarr passes parameters to custom scripts as as environmental variables
# See https://wiki.servarr.com/lidarr/custom-scripts
lidarr = {
    'eventtype':       os.environ.get('lidarr_eventtype'),
    'artist_name':     os.environ.get('lidarr_artist_name'),
    'artist_id':       os.environ.get('lidarr_artist_id'),
    'artist_mbid':     os.environ.get('lidarr_artist_mbid'),
    'album_title':     os.environ.get('lidarr_album_title'),
    'album_id':        os.environ.get('lidarr_album_id'),
    'album_mbid':      os.environ.get('lidarr_album_mbid'),
    'torrent_hash':    os.environ.get('lidarr_download_id'),  # This is the torrent hash
    'addedtrackpaths': os.environ.get('lidarr_addedtrackpaths'),
}

# Print a pretty table with lidarr parameters
msg = ["╔", "║", "║", "║", "╚"]
for key, val in lidarr.items():
    if key in ['artist_name', 'album_title'] or logging.getLogger().isEnabledFor(logging.DEBUG):
        w = max(len(key), len(str(val)))
        msg[0] += "═" * (w + 2) + "╤"
        msg[1] += f" {key.ljust(w)} │"
        msg[2] += "─" * (w + 2) + "┼"
        msg[3] += f" {str(val).ljust(w)} │"
        msg[4] += "═" * (w + 2) + "╧"
msg[0] = msg[0][:-1] + "╗"
msg[1] = msg[1][:-1] + "║"
msg[2] = msg[2][:-1] + "║"
msg[3] = msg[3][:-1] + "║"
msg[4] = msg[4][:-1] + "╝"
logging.info("\n\nStarting auto-beets. Good luck!\n{0}\n".format('\n'.join(msg)))


# %% Read Lidarr's config file to get the base url and api key
with open('/config/config.xml') as f:
    config = f.read()

lidarr_baseUrl = re.findall("<UrlBase>(.*)</UrlBase>", config)[0]
lidarr_port = re.findall("<Port>(.*)</Port>", config)[0]
lidarr_url = f"http://127.0.0.1:{lidarr_port}{lidarr_baseUrl}"

api_keys = {
    "ops": os.environ.get('API_KEY_OPS'),
    "red": os.environ.get('API_KEY_RED'),
    "lidarr": re.findall("<ApiKey>(.*)</ApiKey>", config)[0],
}
for key, val in api_keys.items():
    logging.info(f'{"Found" if val else "Missing"} API key for {key}')

# %% Set headers with lidarr's API key
headers = {
    'Content-Type': 'application/json',
    "X-Api-Key": api_keys["lidarr"],
}

# %% Check that the event type is correct and handle testing
if lidarr['eventtype'] == 'Test':
    if parse_response(requests.get(f'{lidarr_url}/api', headers=headers)):
        logging.info('Auto-beets successfully tested! Take a break and drink some tea!')
        raise SystemExit()
    else:
        logging.error('Something is wrong! Take a break, make some tea, and come back if you feel up for it!')
        raise Exception('Something is wrong!')
elif lidarr['eventtype'] != 'AlbumDownload':
    logging.warning(f"You are running auto-beets on a {lidarr['eventtype']} event!"
                    f" I only know how to work with import/upgrade but I'll try my best!")

# %% Get info about the release
params = {
    'artistId': lidarr['artist_id'],
    'albumId': lidarr['album_id'],
    'eventType': 'Grabbed'
}
albumHistory = parse_response(requests.get(f'{lidarr_url}/api/v1/history/artist', params=params, headers=headers))
if albumHistory:
    torrent_URL = albumHistory[0]['data']['nzbInfoUrl']
else:
    torrent_URL = []
    logging.warning("Can't find the grab event in history!")

# If the hash isn't provided for some reason, look for it
if not lidarr['torrent_hash'] and albumHistory:
    lidarr['torrent_hash'] = albumHistory[0]['downloadId']
elif not lidarr['torrent_hash']:
    params['eventType'] = "trackFileImported"
    albumHistory = parse_response(
        requests.get(f'{lidarr_url}/api/v1/history/artist', params=params, headers=headers))
    lidarr['torrent_hash'] = albumHistory[0]['downloadId']

# %% Get the folder where the album exists
if lidarr['addedtrackpaths']:
    album_path = os.path.dirname(lidarr['addedtrackpaths'].split('|')[0])
else:
    logging.warning("Didn't see lidarr['addedtrackpaths'], getting directory from the API")
    params = {'albumId': lidarr['album_id']}
    trackFile = parse_response(requests.get(f'{lidarr_url}/api/v1/trackFile', params=params, headers=headers))
    album_path = os.path.dirname(trackFile[0]['path'])

logging.info(f"album path = {album_path}")
logging.info(f"torrent url = {torrent_URL}")
logging.info(f"torrent hash = {lidarr['torrent_hash']}")

# %% Download album data from gazelle
if "redacted" in torrent_URL:
    trackers = ["red"]
elif "orpheus" in torrent_URL:
    trackers = ["ops"]
else:
    trackers = [key for key in api_keys if key in ['red', 'ops'] and api_keys[key] is not None]
    if trackers:
        logging.warning(f"Couldn't find the tracker url, trying {' and '.join(trackers).upper()}")

for tracker in trackers:
    origin_file = os.path.join(album_path, "origin-" + tracker + ".yaml")
    if not os.path.isfile(origin_file):
        logging.info(f"Looking for origin data on {tracker.upper()}")
        cmd = ["gazelle-origin", "-o", origin_file, "--tracker", tracker, "--api-key", api_keys[tracker],
               lidarr['torrent_hash']]
        process = subprocess.run(cmd, capture_output=True, text=True)
        if process.returncode:
            logging.warning(f"gazelle-origin-{tracker.upper()}: {process.stderr.strip()}")
        elif os.path.isfile(origin_file):
            logging.info(f'Origin data saved at "{origin_file}"')
            break
    else:
        logging.info(f"Origin data already exists at {origin_file}")

# %% Run beets!
cmd = ["beet", 'import', '-l', '/config/logs/beets.txt', '--flat', '-q', '--nocopy', '--write', album_path]
process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           env=dict(os.environ, BEETSDIR="/beets"))
ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
with process.stdout:
    try:
        for line in iter(process.stdout.readline, b''):
            logging.info(f'\t\t{ansi_escape.sub("", line.decode("utf-8").strip())}')
    except subprocess.CalledProcessError as err:
        logging.exception("Beets error!")

# %% Parse the beets release ID and update the release edition in lidarr so they match (probably no reason to do this)

cmd = ["beet", 'list', '-af', 'id=$mb_albumid', album_path]
process = subprocess.run(cmd, capture_output=True, text=True, env=dict(os.environ, BEETSDIR="/beets"))
musicbrainz_id = re.search('^id=(.+)$', process.stdout, re.M).group(1)

params = {'albumIds': lidarr['album_id']}
album = parse_response(requests.get(f'{lidarr_url}/api/v1/album', params=params, headers=headers))[0]
album["anyReleaseOk"] = False
release_new = release_old = None
for release in album["releases"]:
    if release["monitored"]:
        release_old = release
    release["monitored"] = release['foreignReleaseId'] == musicbrainz_id
    if release["monitored"]:
        release_new = release
if release_new['foreignReleaseId'] != release_old['foreignReleaseId']:
    logging.info(f"Updating lidarr release from https://musicbrainz.org/release/{release_old['foreignReleaseId']} "
                 f"to https://musicbrainz.org/release/{release_new['foreignReleaseId']}")
    parse_response(requests.put(f"{lidarr_url}/api/v1/album", params=params, headers=headers, data=json.dumps(album)))
else:
    logging.info("The lidarr release ID already matches the one from beets, nice!")

logging.info(
    "Finished! I hope your perfectionist soul is satisfied. Rest, you have earned it! And remember to listen, not just catalog!")
