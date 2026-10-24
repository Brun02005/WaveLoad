"""
infrastructure/recycle_bin.py
=============================
Manda archivos a la Papelera de reciclaje de Windows.

WaveLoad nunca borra un archivo del usuario de forma permanente: si se
equivocó, lo restaura desde la Papelera (principio 3 de ARQUITECTURA.md). Usa
``SHFileOperationW`` con ``FOF_ALLOWUNDO``, que es lo que hace el Explorador al
apretar Supr, vía ctypes, sin dependencias nuevas.
"""

import ctypes
import os
import sys
from ctypes import wintypes
from pathlib import Path

_FO_DELETE = 0x0003
_FOF_SILENT = 0x0004
_FOF_NOCONFIRMATION = 0x0010
_FOF_ALLOWUNDO = 0x0040
_FOF_NOERRORUI = 0x0400


class _SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("wFunc", wintypes.UINT),
        ("pFrom", wintypes.LPCWSTR),
        ("pTo", wintypes.LPCWSTR),
        ("fFlags", ctypes.c_ushort),
        ("fAnyOperationsAborted", wintypes.BOOL),
        ("hNameMappings", ctypes.c_void_p),
        ("lpszProgressTitle", wintypes.LPCWSTR),
    ]


def send_to_recycle_bin(path: str | os.PathLike) -> None:
    """Manda ``path`` a la Papelera. Levanta ``OSError`` si no se pudo.

    No pregunta ni muestra diálogos: la confirmación es responsabilidad de
    quien llama, que ya se la pidió al usuario.
    """
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(f"No existe: {target}")
    if sys.platform != "win32":
        raise OSError("La Papelera de reciclaje sólo está soportada en Windows")

    op = _SHFILEOPSTRUCTW()
    op.wFunc = _FO_DELETE
    # pFrom es una lista terminada en doble NUL; ctypes agrega uno.
    op.pFrom = str(target.resolve()) + "\0"
    op.fFlags = _FOF_ALLOWUNDO | _FOF_NOCONFIRMATION | _FOF_SILENT | _FOF_NOERRORUI
    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    if result != 0 or op.fAnyOperationsAborted:
        raise OSError(f"No se pudo mandar a la Papelera (código {result}): {target}")
    if target.exists():
        raise OSError(f"El archivo sigue en su lugar, probablemente está en uso: {target}")
