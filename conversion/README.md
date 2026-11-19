# Maintainer scene conversion

Normal v1.1 installation uses `prepare_game.py`, not this tool.

`restore_campaign_brew.py` reproduces the validated scene migration from an unmodified prepared **v1.0** game directory and the matching BREW main.dz. It rejects other scene profiles and existing output directories. Its result preserves original gameplay component sets, root transforms, non-entity records and known referenced compatibility entities while adopting BREW visual scene layouts and colours.

```sh
python conversion/restore_campaign_brew.py --game /path/to/v1.0/game --brew-main /path/to/BREW/main.dz --output /path/to/new_output
```

The script uses the repository's `asset_tools` modules and Python 3.10+ standard library. No replays are needed to reproduce the asset conversion. Hardware testing established the resulting v1.1 game-data baseline.

To regenerate the v1.1 installation recipe from that prepared output:

```sh
python preparation/build_recipe.py --ngage /path/to/game.n-gage --ios-main /path/to/iOS/main.dz --brew-main /path/to/BREW/main.dz --game-dir /path/to/new_output/game
```

The resulting recipe is deterministic source-copy instructions plus compatibility deltas. Retain all generated output hashes when changing either the source assets or conversion.
