# Code signing policy

Free code signing provided by [SignPath.io](https://signpath.io), certificate by [SignPath Foundation](https://signpath.org).

`Blinkythm.exe` in the Windows release zip is signed with this certificate. It is built from this repository by the GitHub Actions workflow in `.github/workflows/release.yml` and sent to SignPath from that workflow. Nothing built outside that workflow is signed.

## Team roles

- Committers and reviewers: [ehgns-k](https://github.com/ehgns-k)
- Approvers: [ehgns-k](https://github.com/ehgns-k)

Every signing request is approved by hand in SignPath before the signed file is released.

## Privacy policy

This program will not transfer any information to other networked systems unless specifically requested by the user or the person installing or operating it.

Blinkythm has no network features. Webcam frames are processed in memory to measure eye openness and are never saved or sent.
