# Baseline 1.0 checks

* The user completed the campaign on New 3DS without a crash on the preserved gameplay baseline.
* The latest presentation build includes the context mappings, double-buffered lower screen, refined A action texture, console controls and touch keypad.
* The initial loading graphic is 58x15 at (262,225), disappears at the first rendered game frame, and does not change any gameplay rendering path.
* Native build with devkitARM/libctru/mpg123/zlib: passed.
* Portable loading renderer: confirmed only the lower-right rectangle changes and a normal redraw removes the indicator.
* Real-package preparation: all 50 outputs from N-Gage package plus iOS IPA match the tested game files byte-for-byte.
* The public installation package contains no complete game data files; the preparation script and restoration compatibility patches require the user's input copies.
* Previous context hook execution checks cover stock and relocated images. Prompt streams stayed constant throughout sampled menu and gameplay sequences. The VIP keypad replay passed digits, repeated taps, Clear, star/hash, Back and inactive rejection.
* The new loading indicator still awaits final confirmation on hardware.
