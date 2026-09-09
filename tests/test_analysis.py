import warnings

import numpy as np
import pytest
import soundfile as sf
import librosa

from services.analysis_service import AnalysisService

warnings.filterwarnings("ignore")


def _click_wav(bpm, tmp_path):
    sr, dur = 22050, 40
    times = np.arange(1.0, dur, 60.0 / bpm)
    y = librosa.clicks(times=times, sr=sr, click_duration=0.04,
                       length=int(dur * sr)).astype("float32")
    path = tmp_path / f"click_{bpm}.wav"
    sf.write(str(path), y, sr)
    return str(path)


@pytest.mark.parametrize("bpm", [125, 132, 140])
def test_bpm_calibration_within_two(bpm, tmp_path):
    """The prior-bias fix: librosa's default pulled fast tracks toward 120
    (125->123, 132->129). The calibrated estimator must land within ±2."""
    result = AnalysisService.analyze_file(_click_wav(bpm, tmp_path))
    assert abs(result.bpm - bpm) <= 2, f"{bpm} -> {result.bpm}"


def test_result_shape(tmp_path):
    r = AnalysisService.analyze_file(_click_wav(128, tmp_path))
    assert r.key_camelot and r.key_camelot[-1] in ("A", "B")
    assert 1 <= r.energy <= 10
