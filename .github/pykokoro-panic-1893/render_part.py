from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import numpy as np
import soundfile as sf

from pykokoro import KokoroPipeline, PipelineConfig
from pykokoro.generation_config import GenerationConfig

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "temporary/pykokoro-panic-1893/panic_1893_narration.txt"
OUT = Path(os.environ["OUTPUT_DIR"]).resolve()
PART = int(os.environ["PART_INDEX"])
PARTS = int(os.environ["PART_COUNT"])
VOICE = "am_michael"
SPEED = 0.98


def split_units(text: str) -> list[dict[str, object]]:
    units: list[dict[str, object]] = []
    for raw in re.split(r"\n\s*\n+", text):
        raw = raw.strip()
        if not raw:
            continue
        heading = raw.startswith("## ")
        title = raw[3:].strip() if heading else ""
        spoken = (title.rstrip(".") + ".") if heading else raw
        spoken = re.sub(r"\s+", " ", spoken).strip()
        units.append(
            {
                "spoken": spoken,
                "heading": heading,
                "title": title,
                "weight": max(1, len(re.findall(r"\b[\w’'-]+\b", spoken))),
            }
        )
    return units


def partition_ranges(units: list[dict[str, object]], count: int) -> list[tuple[int, int]]:
    if count < 1 or count > len(units):
        raise ValueError("Invalid partition count")
    weights = [int(u["weight"]) for u in units]
    ranges: list[tuple[int, int]] = []
    start = 0
    remaining_weight = sum(weights)
    for index in range(count):
        remaining_parts = count - index
        if remaining_parts == 1:
            end = len(units)
        else:
            target = remaining_weight / remaining_parts
            end = start
            accumulated = 0
            max_end = len(units) - (remaining_parts - 1)
            while end < max_end:
                next_weight = weights[end]
                if end > start and accumulated + next_weight > target:
                    break
                accumulated += next_weight
                end += 1
            if end == start:
                end += 1
        used = sum(weights[start:end])
        ranges.append((start, end))
        start = end
        remaining_weight -= used
    if ranges[0][0] != 0 or ranges[-1][1] != len(units):
        raise RuntimeError("Partition coverage is incomplete")
    for left, right in zip(ranges, ranges[1:]):
        if left[1] != right[0]:
            raise RuntimeError("Partition ranges overlap or contain a gap")
    return ranges


def mono_float32(audio: object) -> np.ndarray:
    data = np.asarray(audio, dtype=np.float32)
    if data.ndim == 2:
        if data.shape[0] <= 8 and data.shape[1] > data.shape[0]:
            data = data.mean(axis=0)
        else:
            data = data.mean(axis=1)
    elif data.ndim > 2:
        data = data.reshape(-1)
    return np.ascontiguousarray(data.reshape(-1), dtype=np.float32)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    all_units = split_units(SOURCE.read_text(encoding="utf-8"))
    ranges = partition_ranges(all_units, PARTS)
    start, end = ranges[PART]
    units = all_units[start:end]
    print(
        f"Rendering part {PART + 1}/{PARTS}: units {start}..{end - 1}, "
        f"words={sum(int(u['weight']) for u in units)}",
        flush=True,
    )

    config = PipelineConfig(
        voice=VOICE,
        model_source="github",
        model_variant="v1.0",
        model_quality="q8",
        provider="cpu",
        retain_segment_audio=False,
        generation=GenerationConfig(
            lang="en-us",
            speed=SPEED,
            pause_mode="auto",
            pause_clause=0.22,
            pause_sentence=0.48,
            pause_paragraph=0.80,
            pause_variance=0.0,
            random_seed=1893,
        ),
    )
    pipeline = KokoroPipeline(config)
    wave_path = OUT / f"part-{PART}.wav"
    manifest_path = OUT / f"part-{PART}.json"
    wav: sf.SoundFile | None = None
    sample_rate: int | None = None
    total_samples = 0
    chapters: list[dict[str, object]] = []
    started = time.monotonic()

    try:
        for local_index, unit in enumerate(units):
            if bool(unit["heading"]):
                chapters.append(
                    {
                        "startSample": total_samples,
                        "title": str(unit["title"]),
                        "globalUnitIndex": start + local_index,
                    }
                )
            spoken = str(unit["spoken"])
            print(
                f"[{PART}:{local_index + 1:02d}/{len(units):02d}] "
                f"{spoken[:70]}{'…' if len(spoken) > 70 else ''}",
                flush=True,
            )
            result = pipeline.run(spoken)
            try:
                audio = mono_float32(result.audio)
                current_rate = int(result.sample_rate)
                if audio.size == 0 or not np.isfinite(audio).all():
                    raise RuntimeError(f"Invalid audio at global unit {start + local_index}")
                if sample_rate is None:
                    sample_rate = current_rate
                    wav = sf.SoundFile(
                        wave_path,
                        mode="w",
                        samplerate=sample_rate,
                        channels=1,
                        subtype="PCM_16",
                        format="WAV",
                    )
                elif current_rate != sample_rate:
                    raise RuntimeError(
                        f"Sample rate changed from {sample_rate} to {current_rate}"
                    )
                assert wav is not None and sample_rate is not None
                wav.write(audio)
                total_samples += int(audio.size)
                silence_seconds = 1.05 if bool(unit["heading"]) else 0.34
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
        raise RuntimeError("No audio was produced")
    duration = total_samples / sample_rate
    manifest = {
        "part": PART,
        "partCount": PARTS,
        "unitStart": start,
        "unitEndExclusive": end,
        "unitCount": len(units),
        "wordCount": sum(int(u["weight"]) for u in units),
        "sampleRate": sample_rate,
        "totalSamples": total_samples,
        "durationSeconds": duration,
        "chapters": chapters,
        "voice": VOICE,
        "model": "v1.0-q8",
        "elapsedSeconds": time.monotonic() - started,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2), flush=True)


if __name__ == "__main__":
    main()
