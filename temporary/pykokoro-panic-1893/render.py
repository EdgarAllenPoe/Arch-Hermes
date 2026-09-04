from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import re
import subprocess
import sys
import time
import traceback
from dataclasses import asdict, is_dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

from pykokoro import KokoroPipeline, PipelineConfig
from pykokoro.generation_config import GenerationConfig

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "panic_1893_narration.txt"
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", ROOT / "output")).resolve()
WAV_PATH = OUTPUT_DIR / "Panic_of_1893_PyKokoro_Male_US.wav"
MP3_PATH = OUTPUT_DIR / "Panic_of_1893_PyKokoro_Male_US.mp3"
FFMETA_PATH = OUTPUT_DIR / "chapters.ffmeta"
VALIDATION_PATH = OUTPUT_DIR / "PyKokoro_validation.json"
FFPROBE_PATH = OUTPUT_DIR / "ffprobe.json"

VOICE = "am_michael"
MODEL_SOURCE = "github"
MODEL_VARIANT = "v1.0"
MODEL_QUALITY = "q8"
PROVIDER = "cpu"
SPEED = 0.98


def log(message: str) -> None:
    print(message, flush=True)


def clean_unit(raw: str) -> tuple[str, bool, str]:
    raw = raw.strip()
    is_heading = raw.startswith("## ")
    if is_heading:
        title = raw[3:].strip()
        spoken = title.rstrip(".") + "."
    else:
        title = ""
        spoken = raw
    spoken = re.sub(r"\s+", " ", spoken).strip()
    return spoken, is_heading, title


def split_units(text: str) -> list[tuple[str, bool, str]]:
    units: list[tuple[str, bool, str]] = []
    for raw in re.split(r"\n\s*\n+", text):
        if not raw.strip():
            continue
        spoken, is_heading, title = clean_unit(raw)
        if spoken:
            units.append((spoken, is_heading, title))
    return units


def mono_float32(audio: object) -> np.ndarray:
    data = np.asarray(audio, dtype=np.float32)
    if data.ndim == 0:
        data = data.reshape(1)
    elif data.ndim == 2:
        # PyKokoro is normally mono. Handle either samples-by-channels or
        # channels-by-samples defensively if a future backend returns 2-D data.
        if data.shape[0] <= 8 and data.shape[1] > data.shape[0]:
            data = data.mean(axis=0)
        else:
            data = data.mean(axis=1)
    elif data.ndim > 2:
        data = data.reshape(-1)
    return np.ascontiguousarray(data.reshape(-1), dtype=np.float32)


def escape_ffmetadata(value: str) -> str:
    value = value.replace("\\", "\\\\")
    for char in ("=", ";", "#"):
        value = value.replace(char, "\\" + char)
    return value.replace("\n", " ").strip()


def write_ffmetadata(chapters: list[tuple[int, str]], total_samples: int, sample_rate: int) -> None:
    lines = [
        ";FFMETADATA1",
        "title=The Panic of 1893",
        "artist=PyKokoro am_michael",
        "album=Historical Reports",
        "comment=Generated with pykokoro 0.8.8, Kokoro v1.0 q8, am_michael",
    ]
    if not chapters:
        chapters = [(0, "The Panic of 1893")]
    total_ms = max(1, round(total_samples * 1000 / sample_rate))
    for index, (start_sample, title) in enumerate(chapters):
        start_ms = round(start_sample * 1000 / sample_rate)
        if index + 1 < len(chapters):
            end_ms = round(chapters[index + 1][0] * 1000 / sample_rate)
        else:
            end_ms = total_ms
        end_ms = max(end_ms, start_ms + 1)
        lines.extend(
            [
                "[CHAPTER]",
                "TIMEBASE=1/1000",
                f"START={start_ms}",
                f"END={end_ms}",
                f"title={escape_ffmetadata(title)}",
            ]
        )
    FFMETA_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_command(command: list[str]) -> None:
    log("Running: " + " ".join(command))
    subprocess.run(command, check=True)


def synthesize() -> tuple[int, int, int, list[tuple[int, str]], float]:
    source_text = SOURCE.read_text(encoding="utf-8")
    units = split_units(source_text)
    if len(units) < 80:
        raise RuntimeError(f"Unexpectedly few narration units: {len(units)}")

    generation = GenerationConfig(
        lang="en-us",
        speed=SPEED,
        pause_mode="auto",
        pause_clause=0.22,
        pause_sentence=0.48,
        pause_paragraph=0.80,
        pause_variance=0.02,
        random_seed=1893,
    )
    config = PipelineConfig(
        voice=VOICE,
        model_source=MODEL_SOURCE,
        model_variant=MODEL_VARIANT,
        model_quality=MODEL_QUALITY,
        provider=PROVIDER,
        retain_segment_audio=False,
        generation=generation,
    )

    log(
        f"Initializing PyKokoro: voice={VOICE}, model={MODEL_VARIANT}/{MODEL_QUALITY}, "
        f"provider={PROVIDER}, units={len(units)}"
    )
    pipeline = KokoroPipeline(config)
    wav: sf.SoundFile | None = None
    sample_rate: int | None = None
    total_samples = 0
    chapters: list[tuple[int, str]] = []
    started = time.monotonic()

    try:
        for index, (spoken, is_heading, title) in enumerate(units, start=1):
            if is_heading:
                chapters.append((total_samples, title))
            preview = spoken[:72] + ("…" if len(spoken) > 72 else "")
            log(f"[{index:03d}/{len(units):03d}] {preview}")

            result = pipeline.run(spoken)
            try:
                current_rate = int(result.sample_rate)
                audio = mono_float32(result.audio)
                if audio.size == 0:
                    raise RuntimeError(f"PyKokoro returned empty audio for unit {index}")
                if not np.isfinite(audio).all():
                    raise RuntimeError(f"PyKokoro returned non-finite samples for unit {index}")

                if sample_rate is None:
                    sample_rate = current_rate
                    wav = sf.SoundFile(
                        WAV_PATH,
                        mode="w",
                        samplerate=sample_rate,
                        channels=1,
                        subtype="PCM_16",
                        format="WAV",
                    )
                    log(f"Writing native {sample_rate} Hz mono PCM narration")
                elif current_rate != sample_rate:
                    raise RuntimeError(
                        f"Sample-rate changed from {sample_rate} to {current_rate} at unit {index}"
                    )

                assert wav is not None
                wav.write(audio)
                total_samples += int(audio.size)

                silence_seconds = 1.05 if is_heading else 0.34
                silence = np.zeros(round(sample_rate * silence_seconds), dtype=np.float32)
                wav.write(silence)
                total_samples += int(silence.size)
            finally:
                release = getattr(result, "release_audio", None)
                if callable(release):
                    release()
    finally:
        if wav is not None:
            wav.flush()
            wav.close()
        pipeline.close()

    if sample_rate is None or total_samples <= 0:
        raise RuntimeError("No narration audio was produced")
    elapsed = time.monotonic() - started
    return sample_rate, total_samples, len(units), chapters, elapsed


def encode_mp3() -> None:
    run_command(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "warning",
            "-i",
            str(WAV_PATH),
            "-i",
            str(FFMETA_PATH),
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
            str(MP3_PATH),
        ]
    )


def probe_and_validate(
    sample_rate: int,
    total_samples: int,
    unit_count: int,
    chapters: list[tuple[int, str]],
    synthesis_seconds: float,
) -> None:
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_chapters",
            "-show_entries",
            "format=duration,size,bit_rate:stream=codec_name,sample_rate,channels,bit_rate",
            "-of",
            "json",
            str(MP3_PATH),
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    FFPROBE_PATH.write_text(probe.stdout, encoding="utf-8")
    probe_data = json.loads(probe.stdout)
    duration = float(probe_data["format"]["duration"])
    size = int(probe_data["format"]["size"])
    streams = probe_data.get("streams", [])
    if not streams or streams[0].get("codec_name") != "mp3":
        raise RuntimeError("Output is not a valid MP3 stream")
    if duration < 1800:
        raise RuntimeError(f"Narration is unexpectedly short: {duration:.1f} seconds")
    if size < 20_000_000:
        raise RuntimeError(f"Narration file is unexpectedly small: {size} bytes")

    # A full decode catches truncation and damaged frames.
    run_command(["ffmpeg", "-v", "error", "-i", str(MP3_PATH), "-f", "null", "-"])

    source_text = SOURCE.read_text(encoding="utf-8")
    words = re.findall(r"\b[\w’'-]+\b", source_text)
    sha256 = hashlib.sha256(MP3_PATH.read_bytes()).hexdigest()
    package_version = importlib.metadata.version("pykokoro")

    validation = {
        "status": "passed",
        "engine": "pykokoro",
        "pykokoroVersion": package_version,
        "model": {
            "source": MODEL_SOURCE,
            "variant": MODEL_VARIANT,
            "quality": MODEL_QUALITY,
            "provider": PROVIDER,
        },
        "voice": {
            "id": VOICE,
            "language": "en-US",
            "gender": "male",
        },
        "generation": {
            "speed": SPEED,
            "sourceWords": len(words),
            "narrationUnits": unit_count,
            "chapterCount": len(chapters),
            "nativeSampleRateHz": sample_rate,
            "nativeSamples": total_samples,
            "synthesisElapsedSeconds": round(synthesis_seconds, 3),
        },
        "mp3": {
            "file": MP3_PATH.name,
            "durationSeconds": round(duration, 3),
            "durationMinutes": round(duration / 60, 3),
            "bytes": size,
            "sha256": sha256,
            "codec": streams[0].get("codec_name"),
            "sampleRateHz": int(streams[0].get("sample_rate", 0)),
            "channels": int(streams[0].get("channels", 0)),
            "bitRate": int(streams[0].get("bit_rate", probe_data["format"].get("bit_rate", 0))),
            "fullDecode": "passed",
        },
    }
    VALIDATION_PATH.write_text(json.dumps(validation, indent=2) + "\n", encoding="utf-8")
    log(json.dumps(validation, indent=2))


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        sample_rate, total_samples, unit_count, chapters, elapsed = synthesize()
        write_ffmetadata(chapters, total_samples, sample_rate)
        encode_mp3()
        probe_and_validate(sample_rate, total_samples, unit_count, chapters, elapsed)
        WAV_PATH.unlink(missing_ok=True)
        log(f"Completed: {MP3_PATH}")
        return 0
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
