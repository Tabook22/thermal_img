"""Read camera metadata and original measurement settings from a DJI R-JPEG."""
from __future__ import annotations

import ctypes
import math
import os
from pathlib import Path
from xml.etree import ElementTree

from PIL import Image


def sdk_measurement_details(path: Path, sdk_executable: Path | None) -> dict:
    if not sdk_executable or not sdk_executable.is_file():
        return {}
    sdk_executable = sdk_executable.resolve()
    library = sdk_executable.parent / "libdirp.dll"
    if not library.is_file() or os.name != "nt":
        return {}
    try:
        with os.add_dll_directory(str(library.parent)):
            api = ctypes.CDLL(str(library))
            api.dirp_create_from_rjpeg.argtypes = [ctypes.c_void_p, ctypes.c_int32, ctypes.POINTER(ctypes.c_void_p)]
            api.dirp_create_from_rjpeg.restype = ctypes.c_int32
            api.dirp_get_measurement_params.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            api.dirp_get_measurement_params.restype = ctypes.c_int32
            api.dirp_get_rjpeg_resolution.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            api.dirp_get_rjpeg_resolution.restype = ctypes.c_int32
            api.dirp_destroy.argtypes = [ctypes.c_void_p]
            api.dirp_destroy.restype = ctypes.c_int32
            data = path.read_bytes()
            buffer = ctypes.create_string_buffer(data)
            handle = ctypes.c_void_p()
            if api.dirp_create_from_rjpeg(buffer, len(data), ctypes.byref(handle)) != 0:
                return {}
            try:
                # The current DJI DIRP structure has five float fields. Reserve extra
                # space for SDK revisions rather than passing a short native buffer.
                values = (ctypes.c_float * 16)()
                resolution = (ctypes.c_int32 * 2)()
                result = {}
                if api.dirp_get_measurement_params(handle, ctypes.byref(values)) == 0:
                    names = ("distance", "humidity", "emissivity", "reflected_temperature", "atmospheric_temperature")
                    result["parameters"] = {name: round(float(values[index]), 4) for index, name in enumerate(names) if math.isfinite(values[index])}
                if api.dirp_get_rjpeg_resolution(handle, ctypes.byref(resolution)) == 0:
                    result["thermal_resolution"] = {"width": int(resolution[0]), "height": int(resolution[1])}
                return result
            finally:
                api.dirp_destroy(handle)
    except (OSError, ValueError, AttributeError):
        return {}


def original_image_details(path: Path, capture: dict, sdk_executable: Path | None) -> dict:
    sdk = sdk_measurement_details(path, sdk_executable)
    with Image.open(path) as image:
        exif = image.getexif()
        camera = exif.get_ifd(34665)
        xmp = {}
        try:
            root = ElementTree.fromstring(image.info.get("xmp", b""))
            for element in root.iter():
                for key, value in element.attrib.items():
                    xmp[key.rsplit("}", 1)[-1]] = value
        except ElementTree.ParseError:
            pass
        resolution = sdk.get("thermal_resolution", {})
        def number(value):
            try:
                result = float(value)
                return result if math.isfinite(result) else None
            except (TypeError, ValueError, ZeroDivisionError):
                return None
        latitude, longitude = capture.get("latitude"), capture.get("longitude")
        return {
            "parameters": sdk.get("parameters", {}),
            "parameter_source": "DJI Thermal SDK" if sdk.get("parameters") else "unavailable",
            "image_info": {
                "model": exif.get(272) or xmp.get("Model"),
                "serial_number": camera.get(42033) or xmp.get("CameraSerialNumber"),
                "focal_length_mm": number(camera.get(37386)),
                "f_number": number(camera.get(33437)),
                "width": resolution.get("width"),
                "height": resolution.get("height"),
                "created": xmp.get("CreateDate") or capture.get("captured_at"),
                "modified": xmp.get("ModifyDate") or exif.get(306),
                "latitude": latitude,
                "longitude": longitude,
            },
        }
