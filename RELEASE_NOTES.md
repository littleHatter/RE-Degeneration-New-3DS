# Resident Evil: Degeneration v1.2

- Hardware-confirmed live switching between Standard (320×240) and Wide (400×240).
- Tap the bottom-left touchscreen graphic to switch. Each launch starts in
  Standard. The toggle is hidden and inactive while the keypad is open.
- Both launcher metadata fields read **Resident Evil: Degeneration**.
- Both install packages use the exact Live Display Toggle Test 1 executable.
- The v1.1 BREW campaign data and three-input preparation recipe are carried forward.

# Resident Evil Degeneration — v1.1

Promotes the completed BREW campaign trial to the release baseline. A full game run on New 3DS completed without errors, with lighting confirmed significantly closer to the N-Gage original.

* Restores authored scene objects and vertex colours in all 12 previously reconstructed main areas.
* Preserves the tested scripts, progression fixes, gameplay components, audio, controls and touchscreen keypad.
* Restores the standard `sdmc:/3ds/res_degene/` installation path.
* Restores both application name metadata fields to `Resident Evil Degeneration`.
* Updates the Python preparation script to reproduce the exact baseline from matching N-Gage, iOS v1.00.00 and extracted BREW inputs.

Release archives:

* `Resident_Evil_New3DS_v1.1_Complete_Install.zip` — prepared installation including game files.
* `Resident_Evil_New3DS_v1.1_Extract_Your_Own_Install.zip` — executable, UI artwork, preparation script and patches; no complete game data files.
* `Resident_Evil_New3DS_v1.1_Source.zip` — GitHub-ready source tree, build/preparation instructions and validation records; no complete game data files.

For upgrades, merge the new `3ds` folder and preserve `3ds/res_degene/user/`. Trial saves can be copied deliberately from the trial application's `user` folder. Full preparation and build instructions are included in README.md and PREPARING_GAME_DATA.md.
