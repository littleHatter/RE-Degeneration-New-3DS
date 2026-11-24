# Resident Evil: Degeneration for New Nintendo 3DS

**Version 1.3**

A native New Nintendo 3DS compatibility port derived from [LeithSilver's MGSM project](https://github.com/LeithSilver/mgsm), with the separately developed Undercover, Pandemonium and Project Gotham Racing runtime improvements.

The full BREW campaign trial was completed on New 3DS hardware from start to finish without errors. Version 1.1 uses those exact game-data files, returning the application to its original name and SD directory.

## Requirements and installation

Requires a New Nintendo 3DS, New 3DS XL or New 2DS XL with the Homebrew Launcher.

* **Complete installation:** extract the archive and merge its `3ds` folder into the SD card root.
* **Installation without game data:** follow [PREPARING_GAME_DATA.md](PREPARING_GAME_DATA.md), run the supplied Python script with your matching input copies, then merge the resulting `3ds` folder into the SD card root.
* **Source:** the GitHub archive includes build source, preparation/conversion tools and prepared UI artwork. It does not include complete original game files. Build instructions are below.

Launch **Resident Evil: Degeneration**. The executable is `3ds/res_degene/res_degene.3dsx` and data lives at `sdmc:/3ds/res_degene/`. Both launcher metadata fields read Resident Evil: Degeneration.

When updating, preserve `3ds/res_degene/user/`, which contains saves and settings. No saves are included. The earlier trial directories are not read automatically. To continue using a save made in the completed campaign trial, copy its `user` folder from `3ds/res_degene_brew_campaign/` into `3ds/res_degene/` after backing up any existing destination save folder. Do not copy the old trial executable or entry scripts.

## Renderer selection

At launch, tap **No** at the lower left for Software or **Yes** at the lower right for Hardware acceleration. Press B to exit the prompt. Relaunch to change the rendering mode.

## Live display toggle

Tap the bottom-left touchscreen graphic to switch between Standard (320×240)
and Wide (400×240). Each launch starts in Standard. The toggle is hidden and
inactive while the keypad is open.

## Bottom-screen map

Tap the bottom-right map button to open or close the map. The keypad takes priority while it is open. The map updates at up to 10 Hz and retains the last completed image between updates. Software mode uses the GPU for map geometry with a software fallback. In Hardware mode the top-screen game renderer uses the GPU and the map uses the 10 Hz CPU rasterizer. The map refreshes merchant and treasure markers during gameplay.

## What changed in v1.1

The 12 reconstructed main scene groups now use the BREW version's authored scene objects, vertex colours and shared-object template layout. These replace the previous lightmap-to-vertex-colour approximations. Native N-Gage model geometry is reused where already compatible. Baggage and the initial VIP scene remain on their original intact assets.

All 329 gameplay-component roots and their tested component data/root transforms are preserved. Scripts, progression fixes, story resources, audio, controls, touch keypad and presentation remain unchanged. Six referenced baseline-only entities are retained for compatibility: four visual objects and two nonvisual entities. Their identities and reasons are documented in `validation/conversion_checks.json` in the source archive.

This release does not copy the BREW executable or replace game scripts wholesale. The tested hybrid retains compatibility resources from the iOS donor, so preparing your own data still needs that donor as well as N-Gage and BREW input copies.

## Controls

| 3DS input | Action |
| --- | --- |
| D-pad / Circle Pad | Movement |
| A or R | Confirm / action / fire |
| Y | Reload weapon |
| L | Use knife / zoom |
| X | Left softkey / aim / exit aim |
| B | Right softkey / Back |
| Start | Pause |
| Select | No action |
| Touchscreen | Phone keypad when the game opens its keypad screen |

The lower screen displays contextual A/A2, B/B2, Start and X1/X2 prompts. The original top-screen softkeys are suppressed, and the touch keypad takes priority over lower-screen artwork. Lift and tap again to repeat a digit. X clears the keypad; B returns. The opening-door action graphic displays A. The startup loading indicator disappears on the first game-rendered frame. HOME provides normal application exit.

A normal game exit returns directly to the launcher.

## Diagnostics

File diagnostics remain at `sdmc:/3ds/res_degene/res_degene.log`. If reporting a fault, copy the log before relaunching and retain any system crash dump. Include the chapter/area and the action that triggered the issue. The lower screen normally shows artwork rather than diagnostics.

## Build

Install devkitARM, libctru, picasso, bin2s and the 3DS citro2d, citro3d, mpg123 and zlib libraries, then run:

```sh
make -C source
```

Copy `source/res_degene.3dsx` and `source/res_degene.smdh` to `3ds/res_degene/`. The packaged `ui` folder is also required. The source package provides ready-to-use UI binaries; regeneration uses Pillow and NumPy via `asset_tools/build_bottomscreen.py` and `asset_tools/build_touch_keypad.py`.

Game preparation uses **Python 3.10+ and the standard library only**, with no downloads. The desktop diagnostic probe additionally uses Unicorn 2.1.4: `python source/build_desktop.py`. `RE_CONSOLE_UI=1` enables the console display adaptations on desktop. Offline historical lighting tools use NumPy/SciPy; normal preparation does not run those tools.

`preparation/build_recipe.py` regenerates the verified copy/patch recipe from prepared data and the three original source archives. `conversion/restore_campaign_brew.py` records the scene-conversion process from prepared **v1.0** data; its use is for maintenance, not the normal v1.1 installation path. See `conversion/README.md`.

## Credits and licensing

The inherited GPL license is included in LICENSE; dependency notices are in THIRD_PARTY.md and the bundled third_party directories. Original game content and supplied presentation artwork retain their respective rights and are separate from the compatibility source license. No complete game data files are included in the source or extract-your-own installation packages.
