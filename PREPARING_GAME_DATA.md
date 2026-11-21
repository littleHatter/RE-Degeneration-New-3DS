# Preparing Resident Evil: Degeneration game data for v1.2

Use **Python 3.10 or later**. The supplied script uses the standard library only and does not download anything.

## Required input copies

| Version | Accepted input | Used for |
| --- | --- | --- |
| Tested N-Gage 2.0 edition | `.n-gage` package, or extracted native game directory | Native executable, archives and original resources |
| iOS **v1.00.00, OS 2.1 release** | `.ipa`, extracted app directory, or its `main.dz` | Retained compatibility resources from the tested hybrid |
| Verified BREW edition containing `biohazard.s3e` and `main.dz` | Extracted `ResidentEvil/main.dz`, containing directory, or a ZIP containing that file | Authored scene objects, template layout and vertex colours |

The tested BREW copy was distributed as a RAR containing `ResidentEvil/biohazard.s3e`, `ResidentEvil/biohazard.mod`, `ResidentEvil/biohazard.mdc` and `ResidentEvil/main.dz`. **Extract that RAR with your archive utility first.** The preparation script does not require or run the BREW executable and does not decode RAR archives itself. Point `--brew` to the extracted main.dz, not to the N-Gage or iOS archive of the same filename.

All three inputs are required to reproduce this hardware-tested baseline. An Android package is not needed. The script checks content hashes, not filenames; renaming an unsupported release does not make it compatible. Exact supported archive/payload fingerprints are listed in SUPPORTED_INPUTS.json.

## Prepare and install

Unzip the extract-your-own installation package. Keep `prepare_game.py` and its `preparation` folder together. From that directory, run:

```sh
python prepare_game.py --ngage "Resident.Evil.Degeneration.n-gage" --ios "Resident_Evil_DEGENERATION_v1.00.00_os21.ipa" --brew "ResidentEvil/main.dz"
```

On Windows you may use `py -3` instead of `python`. Quote paths containing spaces. The default output is `3ds/res_degene/game/` beside the script.

After the script reports that all 50 files match, merge the supplied `3ds` folder into the SD card root. The executable, metadata and complete `ui` folder are required as well as the game directory. Preserve existing `3ds/res_degene/user` saves/settings.

To prepare directly onto an SD card instead:

```sh
python prepare_game.py --ngage "game.n-gage" --ios "game.ipa" --brew "ResidentEvil/main.dz" --output "E:/3ds/res_degene/game"
```

Copy the package's executable/metadata and `ui` files onto the card too.

## Verification and errors

To validate your inputs and reconstruct in memory without writing game files:

```sh
python prepare_game.py --ngage "game.n-gage" --ios "game.ipa" --brew "ResidentEvil/main.dz" --verify-only
```

The script verifies all input resources used by the restoration recipe and every final output hash. It validates the full result before replacing game files and never accesses the separate `user` save directory. Re-running with the same inputs reproduces the same game data.

If an input is rejected, check its platform/release and use the displayed error to identify the failing input. Keep the original files. No output game files are written until all 50 reconstructed files pass verification.

The included recipe consists of source-copy instructions and compatibility patch data. It contains no complete executable, archive or restored resource file, and every output requires source data from your input copies. It reproduces the exact game files from the successful full-campaign hardware trial without requiring users to run the research conversion or lighting-bake toolchain.
