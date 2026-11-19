# Prepare your own game data

Use Python 3.10 or later. The script uses only the standard library and works with local files; it does not download anything.

You need both:

* Your Resident Evil Degeneration N-Gage 2.0 `.n-gage` package.
* Your matching Resident Evil Degeneration iOS **v1.00.00** `.ipa`, or its extracted `main.dz`. The tested donor was the OS 2.1 release.

The N-Gage resources have damaged sections, so extraction of that package alone is insufficient for this hybrid restoration. The iOS copy supplies the donor data. An Android package is not required by this preparation recipe.

Unzip the installation archive, then run from its directory:

```sh
python prepare_game.py --ngage "Resident.Evil.Degeneration.n-gage" --ios "Resident_Evil_DEGENERATION_v1.00.00_os21.ipa"
```

On Windows, `py -3` may be used instead of `python`. Paths may include spaces if quoted. By default the script fills `3ds/res_degene/game/` beside itself. You can instead name an SD card game directory:

```sh
python prepare_game.py --ngage "game.n-gage" --ios "game.ipa" --output "E:/3ds/res_degene/game"
```

Then copy the supplied `3ds` folder onto the SD card, preserving existing saves. The executable and `ui` files are required as well as the prepared game folder.

Already extracted inputs are also accepted: `--ngage` can point to a directory containing the native game files and `--ios` to the extracted iOS app directory or its `main.dz`. The script checks exact content hashes, not just filenames. A different release or incomplete copy will be rejected; do not rename unrelated files to make them appear compatible.

The included restoration recipe consists of source-copy instructions and compatibility patch data. It contains no complete executable, archive, or restored resource file. The matching input copies are required to produce all 50 final files. This avoids running the research conversion and lighting-bake toolchain on each user's machine, and reproduces the tested baseline byte-for-byte. All input resources used by the recipe and all output files are verified. Preparation validates every output before replacing any game files, and never accesses the separate `user/` save directory.

To verify inputs without writing output:

```sh
python prepare_game.py --ngage "game.n-gage" --ios "game.ipa" --verify-only
```

If preparation fails, retain the original input files and the displayed error. No game files are written until the complete reconstruction has passed verification.
