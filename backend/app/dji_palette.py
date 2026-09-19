"""Read DJI's official 10 x 256 pseudo-color LUT from a radiometric JPEG."""
from __future__ import annotations

import ctypes
from functools import lru_cache
from pathlib import Path

import numpy as np


PALETTE_NAMES = ("white_hot", "fulgurite", "iron_red", "hot_iron", "medical",
                 "arctic", "rainbow1", "rainbow2", "tint", "black_hot")


class _PseudoColorLut(ctypes.Structure):
    _fields_ = [("red", (ctypes.c_uint8 * 256) * 10),
                ("green", (ctypes.c_uint8 * 256) * 10),
                ("blue", (ctypes.c_uint8 * 256) * 10)]


@lru_cache(maxsize=32)
def _load(source_name: str, source_mtime_ns: int, executable_name: str) -> dict[str, np.ndarray] | None:
    del source_mtime_ns  # Included in the cache key so replacing a source invalidates its LUT.
    source, executable = Path(source_name), Path(executable_name)
    library = executable.parent / ("libdirp.dll" if executable.suffix.lower() == ".exe" else "libdirp.so")
    if not source.is_file() or not library.is_file():
        return None
    handle = ctypes.c_void_p()
    try:
        if library.suffix == ".dll" and hasattr(ctypes, "WinDLL"):
            dll_directory = getattr(__import__('os'), 'add_dll_directory', None)
            context = dll_directory(str(library.parent)) if dll_directory else None
            api = ctypes.WinDLL(str(library))
            if context:
                context.close()
        else:
            api = ctypes.CDLL(str(library))
        api.dirp_create_from_rjpeg.argtypes = [ctypes.c_void_p, ctypes.c_int32, ctypes.POINTER(ctypes.c_void_p)]
        api.dirp_create_from_rjpeg.restype = ctypes.c_int32
        api.dirp_get_pseudo_color_lut.argtypes = [ctypes.c_void_p, ctypes.POINTER(_PseudoColorLut)]
        api.dirp_get_pseudo_color_lut.restype = ctypes.c_int32
        api.dirp_destroy.argtypes = [ctypes.c_void_p]
        api.dirp_destroy.restype = ctypes.c_int32
        data = source.read_bytes()
        buffer = ctypes.create_string_buffer(data)
        if api.dirp_create_from_rjpeg(buffer, len(data), ctypes.byref(handle)) != 0:
            return None
        lut = _PseudoColorLut()
        if api.dirp_get_pseudo_color_lut(handle, ctypes.byref(lut)) != 0:
            return None
        return {name: np.column_stack((np.ctypeslib.as_array(lut.red[index]),
                                       np.ctypeslib.as_array(lut.green[index]),
                                       np.ctypeslib.as_array(lut.blue[index]))).copy()
                for index, name in enumerate(PALETTE_NAMES)}
    except (OSError, ValueError, AttributeError):
        return None
    finally:
        if handle.value:
            try:
                api.dirp_destroy(handle)
            except (OSError, AttributeError):
                pass


def official_palette_luts(source: Path, sdk_executable: Path | None) -> dict[str, np.ndarray] | None:
    """Return the official DJI LUTs when the licensed SDK and a valid R-JPEG are available."""
    if sdk_executable is None:
        return None
    try:
        return _load(str(source.resolve()), source.stat().st_mtime_ns, str(sdk_executable.resolve()))
    except OSError:
        return None
