# Arch-Hermes: Minimal Arch Wi-Fi + SSH Bootstrap ISO

This repository now builds a deliberately small **first-stage installer** for a dedicated Hermes computer.

The ISO does **not** install Hermes. Its only job is to establish a trustworthy remote-administration foundation:

1. Boot a custom ArchISO in UEFI mode.
2. Connect to a normal password-protected Wi-Fi network through NetworkManager.
3. Prove live routing, DNS, HTTPS, and connection-profile persistence.
4. Erase one explicitly selected internal disk after the operator types `ERASE`.
5. Install console-only Arch Linux, NetworkManager, and OpenSSH.
6. Enable temporary root password SSH access.
7. Reboot from the internal disk.
8. Wait for a **real accepted remote root SSH login** before displaying `SSH VERIFIED`.

Hermes installation, ChatGPT/Codex OAuth, model selection, tools, and system customization happen later over the verified SSH connection.

## Installed system

- UEFI with GPT
- systemd-boot
- ext4 root filesystem
- no encryption
- no swap
- no graphical desktop
- no normal user account
- NetworkManager with an automatically reconnecting system Wi-Fi profile
- NetworkManager-owned `/etc/resolv.conf` (`dns=default`, `rc-manager=file`)
- OpenSSH enabled on port 22
- temporary `PermitRootLogin yes` and `PasswordAuthentication yes`
- first-console-login Wi-Fi/SSH verification program

## Safety boundaries

The installer never automatically chooses a target disk. It hides removable disks, excludes the detected installer disk, displays the selected disk and partitions, and requires the exact word:

```text
ERASE
```

There is no automatic resume or hidden repair path. A failed installation stops and requires a fresh USB boot before another destructive attempt.

## Build with GitHub Actions

Open the repository's **Actions** tab and run **Build Arch Wi-Fi and SSH ISO**. A successful main-branch run uploads an artifact named:

```text
arch-ssh-bootstrap-<run-number>
```

The artifact contains the ISO and its `.sha256` checksum.

The workflow performs four layers of validation:

1. Bash syntax and static safety invariants.
2. Unit-style tests for network and accepted-login detection.
3. A disposable Arch target-root integration test that starts the configured `sshd` and completes a real root password SSH login through it.
4. Full ArchISO construction, embedded-file inspection, checksum verification, and a UEFI QEMU boot smoke test that proves the live installer service starts.

The virtual tests cannot emulate the target laptop's physical Wi-Fi radio. The installer therefore performs the real Wi-Fi, DNS, HTTPS, profile-persistence, and post-reboot SSH tests on the target hardware before reporting success.

## Write the USB

Use Rufus or balenaEtcher to write the ISO as a disk image. Boot the target laptop in UEFI mode with Secure Boot disabled, then select:

```text
Arch Linux install medium (x86_64, UEFI)
```

The installer starts automatically on tty1. tty2 and later consoles remain available for recovery.

## First hard-drive boot

After installation:

1. Remove the USB.
2. Boot the internal drive.
3. Log in locally as `root`.
4. The first-boot verifier starts on tty1.
5. It restores the saved NetworkManager connection, checks routing/DNS/HTTPS, validates and starts `sshd`, and displays the laptop's IP address.
6. From Windows, run the displayed command, for example:

```powershell
ssh root@192.168.1.42
```

7. Leave the SSH session open until the laptop displays:

```text
SSH VERIFIED
```

Only then should Hermes installation begin.

## Security after bootstrap

Root password SSH is intentionally temporary. After key-based SSH access is tested, replace it with public-key authentication and disable both root password login and password authentication.
