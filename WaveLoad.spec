# -*- mode: python ; coding: utf-8 -*-
# Dynamically detect ffmpeg/ffprobe, and bundle the heavy analysis stack
# (librosa/scipy/scikit-learn/soundfile/networkx) which PyInstaller can't
# fully trace on its own.

import shutil
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules


def _find_binary(name: str) -> str:
    """Find a binary on PATH or in common Windows install locations."""
    found = shutil.which(name)
    if found:
        return found
    candidates = [
        rf"C:\ffmpeg\bin\{name}.exe",
        rf"C:\Program Files\ffmpeg\bin\{name}.exe",
        rf"C:\Program Files (x86)\ffmpeg\bin\{name}.exe",
    ]
    for path in candidates:
        if Path(path).exists():
            return path
    raise FileNotFoundError(
        f"{name} not found on PATH or in common locations. "
        f"Install ffmpeg and add it to your PATH, or place it in C:\\ffmpeg\\bin\\"
    )


_ffmpeg = _find_binary("ffmpeg")
_ffprobe = _find_binary("ffprobe")

datas = [
    ('ui/waveload_icon.png', 'ui'),
    ('waveload_icon.ico', '.'),
]
binaries = [(_ffmpeg, '.'), (_ffprobe, '.')]
hiddenimports = [
    'mutagen', 'mutagen.id3', 'mutagen.mp3',
    'PIL', 'PIL.Image', 'PIL.JpegImagePlugin',
    'aiohttp', 'aiohttp.streams',
    'browser_cookie3',
]

# Only full-collect what PyInstaller can't trace on its own. scipy / numpy have
# their own official hooks, so collecting them here too is redundant and was
# heavy enough to OOM the analysis. sklearn is NOT needed (librosa only imports
# it lazily in functions we don't call).
for _pkg in ('librosa', 'soundfile', 'audioread', 'soxr', 'lazy_loader',
             'pooch', 'joblib', 'msgpack'):
    _d, _b, _h = collect_all(_pkg)
    datas += _d
    binaries += _b
    hiddenimports += _h

hiddenimports += collect_submodules('networkx')
# Heavy ML libs that happen to be installed but we never use — an optional
# import was dragging multi-GB PyTorch into the build and OOM-ing PyInstaller.
excludes_extra = ['sklearn', 'torch', 'torchaudio', 'torchvision',
                  'tensorflow', 'pandas', 'numba', 'llvmlite']

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'tkinter', 'PyQt5', 'PySide2'] + excludes_extra,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='WaveLoad',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['waveload_icon.ico'],
)
