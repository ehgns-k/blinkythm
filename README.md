# Blinkythm

Blinkythm watches how often you blink through your webcam. When you have been at the screen for a long time and your blink rate drops, it offers a short rhythm game that you play by blinking. Windows only.

There are three minigames (about 35 seconds each) and a medley that plays all three. Blinking is the only input.

License: [MIT](LICENSE). Windows builds are set up to be signed through SignPath once the project is accepted; see the [code signing policy](CODE_SIGNING_POLICY.md).

## Install and run

**Release build:** download `Blinkythm-*-win64.zip` from Releases, unzip it and run `Blinkythm.exe`.

**From source:** Python 3.10 to 3.12 on Windows, with a webcam.

    pip install -r requirements.txt
    python main.py

On first run a setup wizard checks the camera, measures input delay and sets a few options. After that the app lives in the tray. `Blinkythm.bat` starts it without a console window.

Test options:

- `--sim`: no camera. Space stands in for a blink in the game and the wizard.
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
- Each game opens with a 4-beat count-in. The backing track (92, 100 or 112 BPM) and all cues are mixed into one buffer before playback, so a slow frame cannot shift the beat.
- The guide strip at the bottom shows 8 beats at a time. The top row shows cues you have heard, the bottom row where to blink. A blink spot appears only after its cue has played. The guide can be turned off in Settings.
- The result screen shows a stamp, accuracy, grade counts, accuracy per section (per game in the medley) and the timing spread, plus a line on your strongest and weakest section. Best scores are saved per game.
- Every finished game adds a stamp to the 10-slot card on the home screen. There are no daily streaks.

## Game window

The game window uses pygame-ce. Everything is drawn on a 384x216 pixel screen and scaled by the largest whole number that fits the window. The first size is the largest multiple that fits in 80% of the monitor: 4x (1536x864) on 1920x1080 and 8x (3072x1728) on 3840x2160. Resizing the window rescales it, with dark bars filling the rest. F11 toggles fullscreen. Text uses the Galmuri bitmap font, so letters sit on the same pixel grid as the art.

Flow: prompt, home, (game select), play, result, 20 s rest, then home. When the game was opened from the prompt, the window closes after the rest.

| Screen | Keys |
|---|---|
| Home | Enter play today's game, G games, S settings window, Esc close |
| Game select | Left/Right choose, Enter play, M medley, Esc back |
| Play | Esc stop |
| Result | Enter rest your eyes, R again, G games, A apply the suggested offset |
| Rest | Esc skip (not counted as a rest) |

Buttons and game tiles also work with the mouse. The tray, prompt, settings window and calibration wizard are classic Tk windows. While the game window is open it runs its own 60 fps loop inside the Tk main loop and processes Tk events every frame, so the tray menu and settings still respond.

## When the prompt appears

All of these must hold. The values are on the Settings tab.

1. Your face has been visible (screen time) for at least the set time, 20 minutes by default.
2. Blinks in the last minute are below the threshold, 12 per minute by default. No decision is made if your face was visible for less than 40 of the last 60 seconds.
3. No fullscreen game or video and no presentation is running (checked with the Windows notification state API).
4. Any snooze or post-game quiet time has passed.

If your face is gone for 90 seconds, you are treated as away and screen time resets to zero. Finishing a game resets it too. The prompt has no default button, so typing cannot trigger it, and its buttons do nothing for the first 1.2 seconds. With no answer after 90 seconds it counts as a snooze.

## Judging

The input time is the moment your eyes start to close. The detector interpolates where eye openness (EAR) crosses the threshold between two frames, so the time is finer than the 33 ms frame interval of a 30 fps camera. A blink is judged as soon as the closing has been seen in two frames in a row. Events that arrive late keep their original time, so the delay does not affect the result.

| Grade | Distance from the beat | Points |
|---|---|---|
| Perfect | within 70 ms | 100 |
| Good | within 130 ms | 75 |
| Close | within 200 ms | 40 |
| Miss | further | 0 |

- The windows are wider than in keyboard rhythm games because of the webcam frame interval and because people vary more when timing a blink. Cameras slower than 30 fps get wider windows automatically.
- Webcam and audio delay differ between devices. In the wizard you blink along to 8 metronome ticks; the median error, folded by the beat period, is saved as the offset. Uneven results are rejected.
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
    blinkythm/game/app.py      game window: setup, scaling, input, screen changes, running inside Tk
    blinkythm/game/gfx.py      pixel screen, palette, fonts, boxes, buttons, key hints
    blinkythm/game/screens.py  home, game select, play, medley break, result, rest
    blinkythm/game/scenes.py   the three game scenes
    blinkythm/ui_*.py          main window (status/settings), prompt, wizard (Tk)
    blinkythm/winenv.py        work area, fullscreen detection, autostart
    assets/sprites/*.png       pixel art at 1x (drawn at 2x to 4x in the game)
    assets/sounds/*.wav        effects, cues and backing loops (44.1 kHz, 16-bit, mono)
    assets/fonts/              Galmuri bitmap fonts and their license (OFL.txt)
    tools/make_assets.py       generates the PNG and WAV files: python tools/make_assets.py
    tools/make_icon.py         builds the exe icon
    tests/test_core.py         logic tests and headless game-flow tests: python tests/test_core.py
    docs/releases/             release notes, one file per version
    docs/signpath-artifact-configuration.xml   what SignPath signs inside the build
    LICENSE                    MIT license
    CODE_SIGNING_POLICY.md     code signing policy (SignPath)

## Assets

All art and sound were made for this project by `tools/make_assets.py`. Sprites are drawn as character maps; sounds are built from sine waves, noise and decay curves. The random seed is fixed, so running the script again gives the same files. To change an asset, edit the script, run it and commit the output.

The fonts are the bitmap versions of Galmuri 2.40.3 by Lee Minseo (quiple): Galmuri9, 11, 11 Bold and 14. They are under the SIL Open Font License 1.1, taken from the npm package `galmuri`. The full license is in `assets/fonts/OFL.txt`.

## Releases

Pushing a `v*` tag builds the exe and publishes a release. The workflow can also be started by hand with a `tag` input, which creates that tag on the chosen commit. Release notes come from `docs/releases/<tag>.md`. To change the notes of an existing release, edit that file and run the workflow by hand with that `tag` and `notes_only` checked.

## Code signing

Free code signing provided by [SignPath.io](https://signpath.io), certificate by [SignPath Foundation](https://signpath.org). The [code signing policy](CODE_SIGNING_POLICY.md) lists who approves signing and what is signed.

The release workflow signs `Blinkythm.exe` only when these repository settings exist. Until then it builds unsigned releases as before.

| Kind | Name | Value |
|---|---|---|
| Secret | `SIGNPATH_API_TOKEN` | API token of a SignPath CI user that may submit requests |
| Variable | `SIGNPATH_ORGANIZATION_ID` | SignPath organization ID |
| Variable | `SIGNPATH_PROJECT_SLUG` | SignPath project slug |
| Variable | `SIGNPATH_SIGNING_POLICY_SLUG` | signing policy slug, for example `release-signing` |
| Variable | `SIGNPATH_ARTIFACT_CONFIGURATION_SLUG` | slug of the artifact configuration made from `docs/signpath-artifact-configuration.xml` |

The workflow uploads the PyInstaller output as an artifact, submits it to SignPath and waits up to an hour for approval. It checks that the returned `Blinkythm.exe` carries a signature, packages the signed folder, and adds the SignPath attribution line to the release notes.

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

The exe is built with PyInstaller (GPL 2.0 or later with an exception that allows distributing the built program under any license).

## Known limitations

- The development machine has no webcam and no Windows. Detection was tested with synthetic EAR series (30 and 15 fps, device delay, noise), and the screens and flow on a Linux virtual display with keyboard input. On Windows, only the window size calculation for high-DPI monitors was tested.
- Glasses glare, a tilted or turned head and dim light make EAR noisy and lower detection. The open-eye baseline adapts to the last 30 seconds.
- Bluetooth headphones add large, unstable delay. The wizard's spread check rejects such measurements.
- With no audio device on the development machine, the music and effects were checked only by their waveforms (length, peak level, cue positions). The mix still needs a listen on real speakers.
