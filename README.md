beets-lidarr
============

The `beets-lidarr` script automatically run beets [beets](https://beets.readthedocs.io/en/stable/) when Lidarr imports a download. If the download came from a Gazelle-based music tracker, then `beets-lidarr` will query the tracker for the album's release info with [gazelle-origin](https://github.com/x1ppy/gazelle-origin) to improve beets matching accuracy using [beets-originquery](https://github.com/x1ppy/beets-originquery).

## How it works:

- First, `beets-lidarr` retrieves the album's hash and tracker from Lidarr.
    - If Lidarr sent the album to the download client, this script can determine the correct tracker using Lidarr's grab history. If the torrent was manually downloaded, it tries both RED and OPS (provided their API key environmental variables exist).
- Then, the hash and tracker are passed to [gazelle-origin](https://github.com/x1ppy/gazelle-origin), which downloads the album's metadata to a YAML file in the album folder/
- Beets is then run with the [beets-originquery](https://github.com/x1ppy/beets-originquery) plugin, which uses the downloaded metadata in the Musicbrainz search query, and then writes the tags to the files.

## Setup
### docker-compose
- Clone this repo and put `lidarr-beets.py`, `lidarr-beets.sh`, `config.yaml`, and `plugins.yaml` into the folder for the beets database.
  - You can use this with an existing beets database too, but it's probably a good idea to make sure the music paths inside docker match the system.
- If you are using the [linuxserver/lidarr](https://hub.docker.com/r/linuxserver/lidarr) docker image or [lidarr-extended](https://hub.docker.com/r/randomninjaatk/lidarr-extended), you can install all the dependencies with linuxserver's [universal-package-install](https://github.com/linuxserver/docker-mods/tree/universal-package-install) mod, shown below.
- Add `- /path/to/beets-lidarr:/beets` as a volume. This should point to the folder containing the `beets-lidarr` scripts and config.
- Get API keys from your favorite gazelle music trackers and set them as `API_KEY_OPS` and/or `API_KEY_RED` in the environment.
  - Note that `beets-lidarr` will still run and tag music without API keys, it just won't be able to use the tracker's metadata for the beets search.
- Start the container, open Lidarr, and go to `Settings -> Connect -> + -> Custom Script`
  - Set notification triggers to `On Release Import` and `On Upgrade`
  - Set the script path to `beets-lidarr.sh`
  - Test and save
- That's it! Next time Lidarr imports a release, `beets-lidarr` should automatically run! Check `beets-lidarr.txt` in the log section to verify that it's working.

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

The provided beets configuration file `config.yaml` is basically a clone of [this beautiful config](https://github.com/florib779/beets-config) with a few modifications, so everything should work out of the box.

The following are the most important config settings:

`beets-lidarr` calls beets with `--flat --quiet --write`.
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