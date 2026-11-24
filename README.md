# Blinkythm

Blinkythm watches how often you blink through your webcam. When you have been at the screen for a long time and your blink rate drops, it offers a short rhythm game that you play by blinking. Windows only.

There are three minigames (about 35 seconds each) and a medley that plays all three. Blinking is the only input.

License: [MIT](LICENSE). The exe is not code-signed, so Windows SmartScreen may warn on first run; choose "More info" and "Run anyway".

## Install and run

**Release build:** download `Blinkythm-*-win64.zip` from Releases, unzip it and run `Blinkythm.exe`.

**From source:** Python 3.10 to 3.12 on Windows, with a webcam.

    pip install -r requirements.txt
    python tools/get_model.py
    python main.py

`tools/get_model.py` downloads MediaPipe's Face Landmarker model (about 3.7 MB) into `assets/models/`. Blinks are detected much more reliably with it. Without it the app falls back to eye landmarks. The release build includes the model.

On first run, three setup screens check the camera, measure input delay and set a few options. After that the app lives in the tray. `Blinkythm.bat` starts it without a console window.

Test options:

- `--sim`: no camera. Space stands in for a blink.
- `--demo`: the prompt appears after 12 seconds of screen time. Settings are not saved.
- `--background`: start hidden (used by autostart).

## Design goals

| Goal | Meaning | Where it shows |
|---|---|---|
| Health | The point is resting your eyes, not the score | "Your eyes today" on the home screen; a 20-second look-far-away break after each game |
| Casual | Nothing to learn first | One button to play; you cannot fail out; a miss never stops the song |
| Short | Under 40 seconds a game | Play starts after a 4-beat count-in; the medley is opt-in |
| Gentle | No scolding | Stamps read Superb, Nice, Good and Rested; blinks off the beat cost nothing |
| Hands-free | Eyes are enough | Blink twice to press the main button on home, game select and results; your eye state is shown in the corner |

## Minigames

| Game | Type | What you do | Length |
|---|---|---|---|
| Lighthouse | Copy | The lighthouse flashes a rhythm over one bar. Blink it back in the next bar. 6 rounds. | 35 s |
| Owl Choir | Continue | Two owls hoot with a gap between them. Wait the same gap and blink. Gaps are 1, 1/2, 1 1/2 and 2 beats. | 37 s |
| Blink Studio | 2 beats later | A customer rings the desk bell. Blink exactly 2 beats later to take the photo. Bells can overlap or fall between beats. | 33 s |
| Medley | All | The three games in a row with a 3.5 s break between them. | 2 min |

- The home screen suggests the game after the one you played last. Enter, or a double blink, starts it.
- Each game opens with a 4-beat count-in on the song's first downbeat. The song, the count-in and all cues are mixed into one buffer before playback, so a slow frame cannot shift the beat. Each game's tempo is the measured tempo of its song: Lighthouse 92, Owl Choir 87, Blink Studio 102 BPM.
- The guide strip at the bottom shows 8 beats at a time. The top row shows cues you have heard, the bottom row where to blink. A blink spot appears only after its cue has played. The guide can be turned off in Settings.
- The result screen shows a stamp, accuracy, grade counts, accuracy per section (per game in the medley) and the timing spread, plus a line on your strongest and weakest section. Best scores are saved per game.
- Every finished game adds a stamp to the 10-slot card on the home screen. There are no daily streaks.

## Windows

Everything is drawn with pygame-ce in one style: the main window, the setup screens, settings and the reminder popup. Only the tray menu is a standard Windows menu.

The main window draws on a 384x216 pixel screen and scales it by the largest whole number that fits. The first size is the largest multiple that fits in 80% of the monitor: 4x (1536x864) on 1920x1080 and 8x (3072x1728) on 3840x2160. Resizing rescales it, with dark bars filling the rest. F11 toggles fullscreen. Text uses the Galmuri bitmap font, so letters sit on the same pixel grid as the art. Closing the window hides it to the tray; Exit is in the tray menu and at the bottom of Settings.

Flow: reminder, home, (game select), play, result, 20 s rest, then home. When the game was opened from the reminder, the window goes back to the tray after the rest.

| Screen | Keys |
|---|---|
| Home | Enter play today's game, G games, S settings, Esc hide to tray |
| Game select | Left/Right choose, Enter play, M medley, Esc back |
| Play | Esc stop |
| Result | Enter rest your eyes, R again, G games, A apply the suggested offset |
| Rest | Esc skip (not counted as a rest) |
| Settings | Up/Down choose, Left/Right change, Enter toggle or open, Esc back |
| Setup | Enter next, Esc back; Left/Right change the camera on the camera screen; R resets the timing screen |

Buttons, game tiles and settings rows also work with the mouse. The reminder is a small borderless window in the corner of the screen. It does not take keyboard focus and only reacts to the mouse.

The app runs a single loop: 60 fps while a window is visible, 15 fps while it waits in the tray.

## Timing calibration

The timing screen works like the calibration in many rhythm games: a metronome keeps ticking at 60 BPM, one tick per second, and you blink along for as long as you like. The metronome is a one-bar sound looped by the mixer, so it never stops on its own.

A dot circles a ring once per beat and passes the notch at the top on the tick. Each blink leaves a mark on the ring where it landed; older marks fade. The arrow outside the ring points at the offset that would be applied right now and moves as new blinks come in, with its value next to it. It is orange while the value is still unsteady and yellow once it can be used. A dim notch shows the offset currently saved, so you can see how far the new one moves it.

The offset is the median of the last 16 blinks, ignoring blinks more than 150 ms from that median. It can be used once 8 blinks agree within a spread of 90 ms. R starts over. You can measure again at any time from Settings.

## When the prompt appears

All of these must hold. The values are on the Settings tab.

1. Your face has been visible (screen time) for at least the set time, 20 minutes by default.
2. Blinks in the last minute are below the threshold, 12 per minute by default. No decision is made if your face was visible for less than 40 of the last 60 seconds.
3. No fullscreen game or video and no presentation is running (checked with the Windows notification state API).
4. Any snooze or post-game quiet time has passed.

If your face is gone for 90 seconds, you are treated as away and screen time resets to zero. Finishing a game resets it too. The prompt has no default button, so typing cannot trigger it, and its buttons do nothing for the first 1.2 seconds. With no answer after 90 seconds it counts as a snooze.

## Blink detection

Eye openness comes from MediaPipe Face Landmarker's eyeBlinkLeft and eyeBlinkRight scores, from a model trained to recognise blinks. If the model file is missing, the eye aspect ratio (EAR) of FaceMesh landmarks is used instead. Landmarks are smoothed between frames, so fast blinks show up as shallow dips.

- The open-eye level adapts to the last 30 seconds. A frame below a share of it counts as closing: 62% (Low), 72% (Normal) or 78% (High) sensitivity. One frame is enough, because a quick blink often lasts a single frame at 30 fps.
- During games and setup every camera frame is processed; in the background 15 per second. The camera is asked for MJPG at 640x480 and 30 fps with a one-frame buffer.
- The camera screen (first-run setup, or Settings > Check the camera) shows a live graph of eye openness over the last 5 seconds, with the threshold line and a mark for every detected blink, plus a counter. If blinks are missed, raise the sensitivity there and watch the counter. High can count a few false blinks when the signal is noisy.

## Judging

The input time is the moment your eyes start to close. The detector interpolates where eye openness crosses the threshold between two frames, so the time is finer than the 33 ms frame interval of a 30 fps camera. A blink is judged on the first frame that crosses the threshold. Events that arrive late keep their original time, so the delay does not affect the result.

| Grade | Distance from the beat | Points |
|---|---|---|
| Perfect | within 70 ms | 100 |
| Good | within 130 ms | 75 |
| Close | within 200 ms | 40 |
| Miss | further | 0 |

- The windows are wider than in keyboard rhythm games because of the webcam frame interval and because people vary more when timing a blink. Cameras slower than 30 fps get wider windows automatically.
- Webcam and audio delay differ between devices. The timing screen measures the delay (see Timing calibration) and saves it as the offset.
- Normal blinks off the beat are not penalised. A blink that is not within 200 ms of any note is ignored and only counted on the result screen.
- One blink matches at most one note: the nearest one not yet judged. Notes are at least 0.5 s apart in every game, so a blink cannot land on the wrong note (covered by the tests).
- A good hit plays the game's own sound (ship bell, your owl's hoot, the shutter). A Close plays it quietly with a dull thud.
- A miss is final only once the note time, the window and 0.18 s have passed, since blink events can arrive late.
- Closures longer than 0.8 s are left out of the blink statistics (dozing or resting).
- If the average error leans more than 30 ms to one side, the result screen offers to apply it to the offset.
- Stamps: 85% or more Superb, 65% Nice, 40% Good, below that Rested.

## Privacy

Video is used in memory to find eye landmarks and is never saved or sent. The app has no network features.

## Layout

    main.py                    entry point
    blinkythm/detector.py      EAR series -> blinks (adaptive threshold, interpolation)
    blinkythm/monitor.py       screen time, blink rate, prompt conditions
    blinkythm/stages.py        charts for the three games (cues, notes, sections) and instructions
    blinkythm/rhythm.py        judging, section scores, calibration
    blinkythm/audio.py         WAV loading, rendering a game's audio, playback (pygame-ce)
    blinkythm/tracker.py       webcam and MediaPipe, fake tracker for tests
    blinkythm/app.py           main loop, tray icon, reminder scheduling
    blinkythm/game/window.py   main window: scaling, input, screen changes, show and hide
    blinkythm/game/gfx.py      pixel screen, palette, fonts, boxes, buttons, key hints
    blinkythm/game/screens.py  home, game select, play, medley break, result, rest
    blinkythm/game/scenes.py   the three game scenes
    blinkythm/game/system.py   settings and the setup screens (camera, timing, finish)
    blinkythm/game/prompt.py   reminder popup
    blinkythm/winenv.py        work area, fullscreen detection, autostart
    assets/sprites/*.png       pixel art at 1x (drawn at 2x to 4x in the game)
    assets/sounds/*.wav        effects and cues (44.1 kHz, 16-bit, mono)
    assets/music/              songs and jingles (OGG) and music.json, which says what plays where
    assets/fonts/              Galmuri bitmap fonts and their license (OFL.txt)
    tools/make_assets.py       generates the PNG and WAV files: python tools/make_assets.py
    tools/import_music.py      measures, trims, levels and encodes the music: python tools/import_music.py SOURCE_DIR
    tools/make_icon.py         builds the exe icon
    tools/get_model.py         downloads the Face Landmarker model into assets/models/ (not committed)
    tests/test_core.py         logic tests and headless game-flow tests: python tests/test_core.py
    docs/releases/             release notes, one file per version
    LICENSE                    MIT license

## Assets

Sprites and sound effects were made for this project by `tools/make_assets.py`. Sprites are drawn as character maps; effects are built from sine waves, noise and decay curves. The random seed is fixed, so running the script again gives the same files. To change an asset, edit the script, run it and commit the output.

The fonts are the bitmap versions of Galmuri 2.40.3 by Lee Minseo (quiple): Galmuri9, 11, 11 Bold and 14. They are under the SIL Open Font License 1.1, taken from the npm package `galmuri`. The full license is in `assets/fonts/OFL.txt`.

## Music

`assets/music/music.json` lists which piece plays where:

| Where | Role | Source |
|---|---|---|
| Lighthouse | `stage_lighthouse` | BGM_BAR (92 BPM) |
| Owl Choir | `stage_owls` | BGM_COUNSELING (87 BPM) |
| Blink Studio | `stage_photo` | BGM_TUNNEL (102 BPM) |
| Home | `home` | BGM_ENDLESS_GAME |
| Game select | `select` | BGM_OMOCHA |
| Settings and setup | `settings` | BGM_PRACTICE |
| Rest | `rest` | BGM_AMBIENT |
| Result music by rank | `result_great`, `result_good`, `result_try` | BGM_EPILOGUE_GREAT, _GOOD, _BAD |
| Result jingles by rank | `jingle_great`, `jingle_good`, `jingle_try` | JINGLE_EPILOGUE_GREAT, _GOOD, _BAD |
| Between medley games | `jingle_medley` | JINGLE_REMIX |

The calibration screen plays only its metronome. The result screen plays the rank's jingle when the stamp lands, then loops the rank's music.

The source WAV files are not in the repository. To change a piece, edit its `source` in `music.json` and run `python tools/import_music.py SOURCE_DIR` (needs ffmpeg with libvorbis). For game songs the tool:

- finds the tempo and beat grid from note onsets, and the first downbeat from the kick drum;
- checks the tempo does not drift between the two halves of the song;
- trims the song to 80 beats after the downbeat.

For every piece it evens out loudness and writes OGG (quality 5).

A game song should keep a steady tempo and have no silent stretch inside the part the game uses. When the songs were chosen, BGM_BEAT_MACHINE was dropped for Blink Studio because it has a 1.5-second stop 29 seconds in.

## Releases

Pushing a `v*` tag builds the exe and publishes a release. The workflow can also be started by hand with a `tag` input, which creates that tag on the chosen commit. Release notes come from `docs/releases/<tag>.md`. To change the notes of an existing release, edit that file and run the workflow by hand with that `tag` and `notes_only` checked.

## Third-party software

The Windows build bundles these packages. Their licenses as listed on PyPI:

| Package | License |
|---|---|
| mediapipe | Apache 2.0 |
| numpy | BSD-3-Clause (with 0BSD, MIT, Zlib and CC0-1.0 parts) |
| pygame-ce | LGPL 2.1 |
| pystray | LGPL 3.0 |
| Pillow | MIT-CMU |
| Galmuri fonts | SIL Open Font License 1.1 |
| MediaPipe Face Landmarker model (downloaded at build time) | not confirmed, see Known limitations |

The exe is built with PyInstaller (GPL 2.0 or later with an exception that allows distributing the built program under any license).

## Known limitations

- The development machine has no webcam and no Windows. Detection was tested with synthetic EAR series (30 and 15 fps, device delay, noise), and the screens and flow on a Linux virtual display with keyboard input. On Windows, only the window size calculation for high-DPI monitors was tested.
- Glasses glare, a tilted or turned head and dim light make the eye signal noisy and lower detection. The open-eye level adapts to the last 30 seconds.
- Detection was tuned on synthetic signals: short, shallow and smoothed blinks at 30 and 15 fps. How well the blink scores work for a given face and camera still has to be checked on real hardware with the camera screen.
- The Face Landmarker model is downloaded from Google's MediaPipe model storage. Its license could not be confirmed from an official page during development. Check it before relying on it for distribution.
- Bluetooth headphones add large, unstable delay. The timing screen will not accept a measurement until the spread is small.
- The reminder uses an SDL setting so that showing it does not take keyboard focus. This could not be checked on Windows here.
- With no audio device on the development machine, music and effects were checked only by measurement: tempo, beat alignment (within 6 ms of the chart), loudness and silent stretches. The mix and the choice of songs still need a listen on real speakers.
