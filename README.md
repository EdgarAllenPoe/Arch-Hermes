# Arch-Hermes

Build a custom Arch Linux installer ISO for a dedicated, console-only Hermes Agent machine.

The ISO is built in GitHub Actions inside a privileged `archlinux:latest` container, so no local Arch Linux computer is required. The live ISO starts the Hermes installer automatically on `tty1`; recovery consoles remain available on other TTYs.

## Intended target

- Entire target disk may be erased.
- UEFI boot; Secure Boot disabled during installation.
- Wi-Fi only, using `iwd`.
- No desktop environment or display manager.
- Hermes runs as `root`.
- No local model.
- Hermes authenticates to **ChatGPT/Codex Subscription** through device-code OAuth.
- No `OPENAI_API_KEY` is configured.

## Safety boundary

The ISO build is non-destructive. The installer running on the target laptop will not erase a disk until you:

1. choose an eligible internal disk by number, and
2. type the exact word `ERASE`.

The live USB is detected and excluded from target choices, and removable disks are hidden by default.

## Build the ISO

Open **Actions → Build Hermes Arch ISO → Run workflow**, or merge/push a build-related change to `main`.

The workflow:

1. starts an Arch Linux build container;
2. installs current Archiso tooling;
3. reassembles `hermes-install.sh` from `installer-parts/` and verifies its SHA-256;
4. copies Archiso's current `releng` profile;
5. embeds the Hermes installer and its `tty1` systemd service;
6. runs `mkarchiso`;
7. opens the completed ISO and verifies the embedded installer/autostart files; and
8. uploads the `.iso` and `.iso.sha256` as a workflow artifact on `main`/manual builds.

## Why the installer is stored in parts

The source installer is split into numbered text fragments under `installer-parts/` solely to make repository publication and review reliable. `assemble-installer.sh` concatenates them byte-for-byte into `hermes-install.sh` and refuses to proceed unless it matches `installer.sha256`.

You can reconstruct it locally on Linux/macOS/WSL with:

```bash
./assemble-installer.sh
```

## Important files

- `.github/workflows/build-hermes-archiso.yml` — GitHub Actions cloud build
- `assemble-installer.sh` — reconstructs and verifies the installer
- `installer-parts/` — exact source fragments of `hermes-install.sh`
- `installer.sha256` — expected installer checksum
- `build-iso.sh` — stages the custom Archiso profile and runs `mkarchiso`
- `verify-iso.sh` — verifies the actual completed ISO contents
- `overlay/` — live ISO systemd service and launcher
- `verify-download.ps1` — Windows checksum verifier for the downloaded ISO

## After a successful build

Download the `hermes-archiso-<run number>` artifact from the completed Actions run. It contains the ISO and its SHA-256 file. Verify the checksum, write the ISO to USB with Rufus/Etcher, boot the target laptop in UEFI mode, and follow the on-screen installer.
