from __future__ import annotations

from datetime import datetime
from pathlib import Path
import io
import re
import shutil
import subprocess

from PIL import Image


OVERLAY_TIME = re.compile(r"\b(20\d{2})[-/:](\d{2})[-/:](\d{2})\s+(\d{2}):(\d{2}):(\d{2})\b")
OVERLAY_GPS = re.compile(r"([+-]?\d{1,2}[.,]\d{4,8})\s*°?\s*([NS])\s+([+-]?\d{1,3}[.,]\d{4,8})\s*°?\s*([EW])", re.I)
OVERLAY_ELEVATION = re.compile(r"\b(\d+(?:[.,]\d+)?)\s*m\b", re.I)


def read_visible_overlay(image: Image.Image) -> dict:
    """Read camera text printed into the upper-left of a DJI image, if present."""
    executable = shutil.which("tesseract")
    if not executable:
        return {}
    try:
        def recognize(candidate):
            buffer = io.BytesIO()
            candidate.save(buffer, format="PNG")
            completed = subprocess.run([executable, "stdin", "stdout", "--psm", "6"],
                                       input=buffer.getvalue(), capture_output=True, timeout=8, check=True)
            return completed.stdout.decode("utf-8", errors="replace")

        text = recognize(image.crop((0, 0, int(image.width * .55), int(image.height * .25))))
        if not OVERLAY_TIME.search(text) or not OVERLAY_GPS.search(text):
            text += "\n" + recognize(image)
    except (OSError, subprocess.SubprocessError):
        return {}
    found = {}
    if match := OVERLAY_TIME.search(text):
        try:
            found["captured_at"] = datetime(*map(int, match.groups())).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    if match := OVERLAY_GPS.search(text):
        latitude = float(match[1].replace(",", ".")) * (-1 if match[2].upper() == "S" else 1)
        longitude = float(match[3].replace(",", ".")) * (-1 if match[4].upper() == "W" else 1)
        if -90 <= latitude <= 90 and -180 <= longitude <= 180:
            found.update(latitude=latitude, longitude=longitude)
    if match := OVERLAY_ELEVATION.search(text):
        found["elevation_m"] = float(match[1].replace(",", "."))
    return found


def extract_capture_metadata(path: Path) -> dict:
    """Read capture coordinates and local camera time from the original image."""
    result = {"latitude": None, "longitude": None, "captured_at": None, "time_zone": None, "elevation_m": None, "overlay_checked": False}
    try:
        with Image.open(path) as image:
            exif = image.getexif()
            gps = exif.get_ifd(34853)
            if gps and all(gps.get(key) for key in (1, 2, 3, 4)):
                def degrees(parts, hemisphere):
                    value = sum(float(part) / divisor for part, divisor in zip(parts, (1, 60, 3600)))
                    return -value if str(hemisphere).upper() in ("S", "W") else value

                latitude = degrees(gps[2], gps[1])
                longitude = degrees(gps[4], gps[3])
                if -90 <= latitude <= 90 and -180 <= longitude <= 180:
                    result["latitude"], result["longitude"] = latitude, longitude
            if gps and gps.get(6) is not None:
                result["elevation_m"] = float(gps[6]) * (-1 if gps.get(5) == 1 else 1)

            details = exif.get_ifd(34665)
            raw_time = details.get(36867) or details.get(36868) or exif.get(306)
            if raw_time:
                parsed = datetime.strptime(str(raw_time).strip(), "%Y:%m:%d %H:%M:%S")
                result["captured_at"] = parsed.strftime("%Y-%m-%d %H:%M:%S")
                offset = details.get(36881) or details.get(36880)
                if offset:
                    result["time_zone"] = str(offset).strip()
            result.update(read_visible_overlay(image))
            result["overlay_checked"] = True
    except (OSError, ValueError, TypeError, KeyError, ZeroDivisionError):
        pass
    return result


def capture_note_text(capture: dict) -> str:
    latitude, longitude = capture.get("latitude"), capture.get("longitude")
    gps = f"{latitude:.6f}, {longitude:.6f}" if latitude is not None and longitude is not None else "Not recorded"
    timestamp = capture.get("captured_at")
    if timestamp:
        date, time = timestamp.split(" ", 1)
        time += f" {capture['time_zone']}" if capture.get("time_zone") else " (camera time)"
    else:
        date = time = "Not recorded"
    elevation = capture.get("elevation_m")
    altitude_line = f"\nElevation: {elevation:.3f} m" if elevation is not None else ""
    return f"Tower location (GPS): {gps}{altitude_line}\nDate: {date}\nTime: {time}"
