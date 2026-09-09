"""
services/analysis_service.py
============================
Pure (Qt-free) audio analysis: BPM, musical key (Camelot notation) and a
coarse energy estimate for a downloaded/imported audio file.

Uses librosa for beat tracking and chroma extraction, and the
Krumhansl-Kessler key profiles for key detection. Kept free of Qt and of any
persistence concern so it can be unit-tested and reused headlessly.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Shaath key profiles (tuned for electronic/pop music in Ibrahim Shaath's
# KeyFinder work) — noticeably more reliable than Krumhansl-Kessler on EDM.
_MAJOR_PROFILE = [6.6, 2.0, 3.5, 2.3, 4.6, 4.0, 2.5, 5.2, 2.4, 3.7, 2.3, 3.4]
_MINOR_PROFILE = [6.5, 2.7, 3.5, 5.4, 2.6, 3.5, 2.5, 5.2, 4.0, 2.7, 4.3, 3.2]

# pitch-class (0=C .. 11=B) -> Camelot code. Major = "B" ring, minor = "A" ring.
_CAMELOT_MAJOR = {0: "8B", 1: "3B", 2: "10B", 3: "5B", 4: "12B", 5: "7B",
                  6: "2B", 7: "9B", 8: "4B", 9: "11B", 10: "6B", 11: "1B"}
_CAMELOT_MINOR = {9: "8A", 10: "3A", 11: "10A", 0: "5A", 1: "12A", 2: "7A",
                  3: "2A", 4: "9A", 5: "4A", 6: "11A", 7: "6A", 8: "1A"}
_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Load window: decode from the start (mp3 offset-seek is slow) and analyse the
# body of the track, skipping the intro.
_LOAD_SECONDS = 90.0
_SKIP_INTRO_SECONDS = 15.0
_TARGET_SR = 22050

# Energy calibration: RMS of typical masters sits ~0.08 (quiet) .. 0.34 (loud).
_RMS_MIN = 0.08
_RMS_MAX = 0.34


@dataclass(frozen=True)
class AnalysisResult:
    bpm: float            # beats per minute, 1-decimal
    key_camelot: str      # e.g. "8A"
    key_name: str         # e.g. "Am"
    energy: int           # coarse 1..10


class AnalysisService:
    """Extracts BPM / key / energy from an audio file on disk."""

    @staticmethod
    def analyze_file(file_path: Path) -> AnalysisResult:
        # Imported lazily: librosa/numpy are heavy and only needed for analysis.
        import numpy as np  # noqa: PLC0415
        import librosa  # noqa: PLC0415

        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {path}")

        y, sr = librosa.load(str(path), sr=_TARGET_SR, mono=True, duration=_LOAD_SECONDS)
        if y.size == 0:
            raise ValueError("Decoded audio is empty.")
        # Trim the intro if the track is long enough to leave a usable body.
        skip = int(_SKIP_INTRO_SECONDS * sr)
        if y.size > skip + int(20 * sr):
            y = y[skip:]

        bpm = AnalysisService._estimate_bpm(y, sr, np)
        key_camelot, key_name = AnalysisService._estimate_key(y, sr, np, librosa)

        # --- Energy (coarse 1..10 from normalized RMS) ---
        rms = float(np.mean(librosa.feature.rms(y=y)))
        scaled = (rms - _RMS_MIN) / (_RMS_MAX - _RMS_MIN) * 9 + 1
        energy = int(max(1, min(10, round(scaled))))

        return AnalysisResult(bpm=bpm, key_camelot=key_camelot, key_name=key_name, energy=energy)

    @staticmethod
    def _estimate_bpm(y, sr, np) -> float:
        """Tempo estimation calibrated for steady electronic music.

        librosa's default beat_track uses a log-normal tempo prior centred at
        120 BPM that systematically pulls faster tracks *down* (125->123,
        132->129, 144->140). We flatten that prior (std_bpm=16), use a finer hop
        for time resolution, and derive the final BPM from the *mean* of the
        clean inter-beat intervals — averaging out frame quantisation for a
        sub-BPM-accurate result on constant-tempo tracks.
        """
        import librosa  # noqa: PLC0415
        from librosa.feature.rhythm import tempo as _tempo  # noqa: PLC0415
        hop = 256
        oenv = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
        tempo = _tempo(
            onset_envelope=oenv, sr=sr, hop_length=hop,
            start_bpm=125, std_bpm=16, aggregate=np.median,
        )
        bpm = float(np.atleast_1d(tempo)[0])

        _, beats = librosa.beat.beat_track(onset_envelope=oenv, sr=sr, hop_length=hop, bpm=bpm)
        if len(beats) >= 8:
            beat_times = librosa.frames_to_time(beats, sr=sr, hop_length=hop)
            ibi = np.diff(beat_times)
            med = float(np.median(ibi))
            if med > 0:
                # Keep only single-beat intervals; drop missed (~2x) / extra (~0.5x) beats.
                good = ibi[(ibi > 0.75 * med) & (ibi < 1.25 * med)]
                if len(good) >= 6:
                    bpm = 60.0 / float(np.mean(good))

        # Fold into the usual DJ range so half/double-time detections normalise.
        while bpm and bpm < 82:
            bpm *= 2
        while bpm > 185:
            bpm /= 2
        return round(bpm, 1)

    @staticmethod
    def _estimate_key(y, sr, np, librosa):
        """Key detection calibrated for electronic music.

        Two calibrations over the naive approach: (1) tuning correction so a
        track tuned off A440 isn't reported a semitone out (which lands on the
        wrong Camelot code); (2) a CQT chromagram + Shaath key profiles
        correlated across all 24 keys. (Harmonic/percussive separation was
        measured to cost 5-10x the total runtime for a marginal gain, so the
        cheaper tuning-corrected CQT is used instead.)
        """
        tuning = float(librosa.estimate_tuning(y=y, sr=sr))
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr, tuning=tuning).mean(axis=1)

        major = np.asarray(_MAJOR_PROFILE)
        minor = np.asarray(_MINOR_PROFILE)
        best_score = -2.0
        best_tonic = 0
        best_is_minor = False
        for tonic in range(12):
            maj_r = float(np.corrcoef(chroma, np.roll(major, tonic))[0, 1])
            min_r = float(np.corrcoef(chroma, np.roll(minor, tonic))[0, 1])
            if maj_r > best_score:
                best_score, best_tonic, best_is_minor = maj_r, tonic, False
            if min_r > best_score:
                best_score, best_tonic, best_is_minor = min_r, tonic, True

        if best_is_minor:
            return _CAMELOT_MINOR[best_tonic], f"{_NOTE_NAMES[best_tonic]}m"
        return _CAMELOT_MAJOR[best_tonic], _NOTE_NAMES[best_tonic]
