from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[2]
PARTS_ROOT = Path(os.environ["PARTS_ROOT"]).resolve()
OUT = Path(os.environ["OUTPUT_DIR"]).resolve()
PART_COUNT = int(os.environ.get("PART_COUNT", "8"))
SOURCE = ROOT / "temporary/pykokoro-panic-1893/panic_1893_narration.txt"
WAV = OUT / "Panic_of_1893_PyKokoro_Male_US.wav"
MP3 = OUT / "Panic_of_1893_PyKokoro_Male_US.mp3"
FFMETA = OUT / "chapters.ffmeta"
VALIDATION = OUT / "PyKokoro_validation.json"
PROBE = OUT / "ffprobe.json"


def run(command: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    print("Running: " + " ".join(command), flush=True)
    return subprocess.run(
        command,
        check=True,
        text=True,
        capture_output=capture,
    )


def locate(part: int, suffix: str) -> Path:
    candidates = [
        PARTS_ROOT / f"part-{part}" / f"part-{part}.{suffix}",
        PARTS_ROOT / f"part-{part}.{suffix}",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    matches = list(PARTS_ROOT.rglob(f"part-{part}.{suffix}"))
    if len(matches) == 1:
        return matches[0]
    raise FileNotFoundError(f"Could not uniquely locate part-{part}.{suffix}: {matches}")


def escape(value: str) -> str:
    value = value.replace("\\", "\\\\")
    for char in ("=", ";", "#"):
        value = value.replace(char, "\\" + char)
    return value.replace("\n", " ").strip()


def write_metadata(chapters: list[dict[str, object]], total_samples: int, rate: int) -> None:
    lines = [
        ";FFMETADATA1",
        "title=The Panic of 1893",
        "artist=PyKokoro am_michael",
        "album=Historical Reports",
        "comment=Generated with pykokoro 0.8.8, Kokoro v1.0 q8, am_michael",
    ]
    total_ms = max(1, round(total_samples * 1000 / rate))
    for index, chapter in enumerate(chapters):
        start_ms = round(int(chapter["startSample"]) * 1000 / rate)
        if index + 1 < len(chapters):
            end_ms = round(int(chapters[index + 1]["startSample"]) * 1000 / rate)
        else:
            end_ms = total_ms
        end_ms = max(end_ms, start_ms + 1)
        lines.extend(
            [
                "[CHAPTER]",
                "TIMEBASE=1/1000",
                f"START={start_ms}",
                f"END={end_ms}",
                f"title={escape(str(chapter['title']))}",
            ]
        )
    FFMETA.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    manifests: list[dict[str, object]] = []
    for part in range(PART_COUNT):
        manifests.append(json.loads(locate(part, "json").read_text(encoding="utf-8")))

    expected_unit_start = 0
    rates: set[int] = set()
    for part, manifest in enumerate(manifests):
        if int(manifest["part"]) != part:
            raise RuntimeError(f"Manifest part order mismatch at {part}")
        if int(manifest["unitStart"]) != expected_unit_start:
            raise RuntimeError(f"Unit gap before part {part}")
        expected_unit_start = int(manifest["unitEndExclusive"])
        rates.add(int(manifest["sampleRate"]))
    if len(rates) != 1:
        raise RuntimeError(f"Inconsistent sample rates: {rates}")
    sample_rate = rates.pop()

    total_samples = 0
    chapters: list[dict[str, object]] = []
    with sf.SoundFile(
        WAV,
        mode="w",
        samplerate=sample_rate,
        channels=1,
        subtype="PCM_16",
        format="WAV",
    ) as output:
        for part, manifest in enumerate(manifests):
            wave_path = locate(part, "wav")
            part_samples = 0
            with sf.SoundFile(wave_path, mode="r") as source:
                if source.samplerate != sample_rate or source.channels != 1:
                    raise RuntimeError(f"Unexpected audio format in {wave_path}")
                while True:
                    block = source.read(262144, dtype="float32", always_2d=False)
                    if block.size == 0:
                        break
                    block = np.asarray(block, dtype=np.float32).reshape(-1)
                    output.write(block)
                    part_samples += int(block.size)
            declared = int(manifest["totalSamples"])
            if part_samples != declared:
                raise RuntimeError(
                    f"Part {part} sample mismatch: file={part_samples}, manifest={declared}"
                )
            for chapter in manifest.get("chapters", []):
                chapters.append(
                    {
                        "startSample": total_samples + int(chapter["startSample"]),
                        "title": str(chapter["title"]),
                        "globalUnitIndex": int(chapter["globalUnitIndex"]),
                    }
                )
            total_samples += part_samples

    if total_samples != sum(int(m["totalSamples"]) for m in manifests):
        raise RuntimeError("Merged sample count mismatch")
    if not chapters or int(chapters[0]["startSample"]) != 0:
        raise RuntimeError("The first chapter does not begin at sample zero")
    write_metadata(chapters, total_samples, sample_rate)

    run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "warning",
            "-i",
            str(WAV),
            "-i",
            str(FFMETA),
            "-map",
            "0:a:0",
            "-map_metadata",
            "1",
            "-map_chapters",
            "1",
            "-af",
            "highpass=f=48,loudnorm=I=-18:TP=-2:LRA=11",
            "-codec:a",
            "libmp3lame",
            "-b:a",
            "128k",
            "-ar",
            "24000",
            "-ac",
            "1",
            "-id3v2_version",
            "3",
            "-metadata",
            "title=The Panic of 1893",
            "-metadata",
            "artist=PyKokoro am_michael",
            "-metadata",
            "album=Historical Reports",
            "-metadata",
            "comment=PyKokoro 0.8.8; Kokoro v1.0 q8; American male voice am_michael",
            str(MP3),
        ]
    )

    probe = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_chapters",
            "-show_entries",
            "format=duration,size,bit_rate:stream=codec_name,sample_rate,channels,bit_rate",
            "-of",
            "json",
            str(MP3),
        ],
        capture=True,
    )
    PROBE.write_text(probe.stdout, encoding="utf-8")
    data = json.loads(probe.stdout)
    stream = data["streams"][0]
    duration = float(data["format"]["duration"])
    size = int(data["format"]["size"])
    if stream.get("codec_name") != "mp3":
        raise RuntimeError("Output codec is not MP3")
    if duration < 1800:
        raise RuntimeError(f"Narration is unexpectedly short: {duration:.1f}s")
    if size < 20_000_000:
        raise RuntimeError(f"Narration is unexpectedly small: {size} bytes")
    if len(data.get("chapters", [])) != len(chapters):
        raise RuntimeError("Embedded chapter count mismatch")
    run(["ffmpeg", "-v", "error", "-i", str(MP3), "-f", "null", "-"])

    source_words = len(re.findall(r"\b[\w’'-]+\b", SOURCE.read_text(encoding="utf-8")))
    validation = {
        "status": "passed",
        "engine": "pykokoro",
        "pykokoroVersion": "0.8.8",
        "model": {
            "source": "github",
            "variant": "v1.0",
            "quality": "q8",
            "provider": "cpu",
        },
        "voice": {"id": "am_michael", "language": "en-US", "gender": "male"},
        "generation": {
            "speed": 0.98,
            "sourceWords": source_words,
            "narrationUnits": sum(int(m["unitCount"]) for m in manifests),
            "chapterCount": len(chapters),
            "nativeSampleRateHz": sample_rate,
            "nativeSamples": total_samples,
            "partCount": PART_COUNT,
            "partElapsedSeconds": [round(float(m["elapsedSeconds"]), 3) for m in manifests],
        },
        "mp3": {
            "file": MP3.name,
            "durationSeconds": round(duration, 3),
            "durationMinutes": round(duration / 60, 3),
            "bytes": size,
            "sha256": hashlib.sha256(MP3.read_bytes()).hexdigest(),
            "codec": stream.get("codec_name"),
            "sampleRateHz": int(stream.get("sample_rate", 0)),
            "channels": int(stream.get("channels", 0)),
            "bitRate": int(stream.get("bit_rate", data["format"].get("bit_rate", 0))),
            "fullDecode": "passed",
        },
    }
    VALIDATION.write_text(json.dumps(validation, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(validation, indent=2), flush=True)
    WAV.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
