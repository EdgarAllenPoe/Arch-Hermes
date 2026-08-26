# Build references

Verified 2026-08-25.

- Archiso project: https://github.com/archlinux/archiso
- ArchWiki Archiso: https://wiki.archlinux.org/title/Archiso
- GitHub Docs — adding/uploading files: https://docs.github.com/en/repositories/working-with-files/managing-files/adding-a-file-to-a-repository
- GitHub Actions artifact upload action: https://github.com/actions/upload-artifact

The official Archiso project states that image creation is supported on Arch Linux and that the `releng` profile is the basis for the monthly Arch installation medium. The included GitHub Actions workflow therefore runs the build in an Arch Linux container rather than attempting to run `mkarchiso` directly on Windows or another host OS.
