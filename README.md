beets-lidarr
============

This is a script for use with Lidarr to automatically grab album information from your favorite Gazelle-based music trackers with [gazelle-origin](https://github.com/x1ppy/gazelle-origin), and tags the files with beets using the metadata from the tracker to improve accuracy with [beets-originquery](https://github.com/x1ppy/beets-originquery).

## How it works:

- First, `lidarr-beets` gets the album's hash and tracker
    - If Lidarr sent the album to the download client, this script can determine the correct tracker from with Lidarr's grab history. If the torrent was manually downloaded, it tries both RED and OPS (provided their API key environmental variables exist).
    - Lidarr logs the hash when the download is imported
- Then, we pass the hash and tracker to [gazelle-origin](https://github.com/x1ppy/gazelle-origin), which downloads the album's metadata to a yaml file in the album folder/
- Run beets with the [beets-originquery](https://github.com/x1ppy/beets-originquery) plugin, which uses the downloaded metadata to find the release in Musicbrainz, and write the tags to the files.
- Finally, update the release version in Lidarr to match what beets detected (probably not necessary).

## Setup

`lidarr-beets` can work with an existing beets database, but it doesn't need it.



### docker-compose
- Clone this repo or put `lidarr-beets.py`, `lidarr-beets.sh`, `config.yaml`, and `plugins.yaml` into a folder where the beets database will exist.
  - You can use this with an existing beets database too, but it's probably a good idea to make sure the music paths inside docker match the system.
- If you are using the [linuxserver/lidarr](https://hub.docker.com/r/linuxserver/lidarr) docker image or [lidarr-extended](https://hub.docker.com/r/randomninjaatk/lidarr-extended), you can install all the dependencies with linuxserver's [universal-package-install](https://github.com/linuxserver/docker-mods/tree/universal-package-install) mod, shown below.
- Add `- /path/to/beets-lidarr:/beets` as a volume. This should point to the folder containing the `beets-lidarr` scripts and config.
- Get API keys from your favorite gazelle music trackers and set them as `API_KEY_OPS` and/or `API_KEY_RED` in the environment.
  - Note that `beets-lidarr` will still run and tag music without API keys, it just won't be able to use the tracker's metadata for the beets search.
- Start the container, open Lidarr, and go to `Setting -> Connect -> + -> Custom Script`
  - Set notification triggers to `On Release Import` and `On Upgrade`
  - Set the script path to `beets-lidarr.sh`
  - Test and save
- That's it! Next time Lidarr imports a release, `beets-lidarr` should automatically run! To verify that it's working, check `beets-lidarr.txt` in the log section.

~~~
  lidarr:
    image: lscr.io/linuxserver/lidarr:latest (or randomninjaatk/lidarr-extended:latest)
    container_name: lidarr
    volumes:
      - /config, /music, /downloads etc.
      - /path/to/beets:/beets
    environment:
      - API_KEY_RED=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
      - API_KEY_OPS=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
      - DOCKER_MODS=linuxserver/mods:universal-package-install
      - INSTALL_PIP_PACKAGES=git+https://github.com/beetbox/beets.git|git+https://github.com/MxMarx/gazelle-origin@orpheus|git+https://github.com/MxMarx/beets-originquery|pyacoustid|beetcamp|pylast|python3-discogs-client 
      - INSTALL_PACKAGES=git|ffmpeg|flac|imagemagick
~~~

 If you are using [theme.park](https://docs.theme-park.dev/themes/lidarr/), you can add universal-package-install like this: `- DOCKER_MODS=ghcr.io/gilbn/theme.park:lidarr|linuxserver/mods:universal-package-install`


## Beets Config

The provided beets configuration file, `config.yaml`, is basically a clone of [this beautiful config](https://github.com/florib779/beets-config) with a few modifications, so everything should work out of the box.

The following are the most important config settings:


`beets-lidarr` calls beets with `--nocopy --flat --quiet --write`. Make sure "move" is set to "no" in your config.
~~~
import:
  write: yes
  copy: no
  move: no
  resume: no
  duplicate_action: remove      # Probably not necessary unless you use an preexisting beets database
~~~

If tagging is enabled in Lidarr, tracks might already be tagged with a musicbrainz ID. To get around this, lower the album_id weight so beets has a chance to change it.
~~~
match:
  distance_weights:
    album_id: 0.01
~~~

~~~
musicbrainz:
  searchlimit: 20            # Recommendation from: https://github.com/kernitus/beets-oldestdate
  extra_tags:                # Enable improved MediaBrainz queries from tags.
    [
      catalognum,
      country,
      label,
      media,
      year
    ]

originquery:                 # Get tags from gazelle-origin  
    origin_file: origin-*.yaml
    use_origin_on_conflict: yes
    tag_patterns:
        media: '$.Media'
        year: '$."Edition year"'
        label: '$."Record label"'
        catalognum: '$."Catalog number"'
        albumdisambig: '$.Edition'      
~~~