from __future__ import annotations
import asyncio, re, subprocess, tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
import numpy as np
from PIL import Image, UnidentifiedImageError

class DecodeError(RuntimeError): pass
class UnsupportedThermalImage(DecodeError): pass

@dataclass
class DecodeResult:
    camera_model: str | None; sdk_version: str; width: int; height: int; temperatures: np.ndarray; valid_mask: np.ndarray
    parameters: dict; provenance: dict; ranges: dict = field(default_factory=dict); warnings: list[str] = field(default_factory=list); metadata: dict = field(default_factory=dict)

class ThermalDecoder(ABC):
    @abstractmethod
    def decode(self, source: Path, parameters: dict) -> DecodeResult: ...

class DjiCliDecoder(ThermalDecoder):
    """Adapter for DJI's official dji_irp sample utility; arguments match SDK v1.8."""
    def __init__(self, executable: Path, version: str, timeout: int = 45): self.executable, self.version, self.timeout = executable, version, timeout
    def available(self): return self.executable.is_file()
    def decode(self, source: Path, parameters: dict) -> DecodeResult:
        if not self.available(): raise DecodeError("DJI Thermal SDK executable is unavailable")
        source = source.resolve()
        if not source.is_file(): raise DecodeError(f"Source image is missing from managed storage: {source.name}")
        with tempfile.TemporaryDirectory(prefix="tower-thermal-") as tmp:
            output = Path(tmp) / "measure.raw"
            cmd = [str(self.executable), "-s", str(source), "-a", "measure", "-o", str(output), "--measurefmt", "float32"]
            flags = {"distance":"--distance", "humidity":"--humidity", "emissivity":"--emissivity", "atmospheric_temperature":"--ambient", "reflected_temperature":"--reflection"}
            for key, flag in flags.items():
                if parameters.get(key) is not None: cmd += [flag, str(parameters[key])]
            try: proc = subprocess.run(cmd, cwd=self.executable.parent, capture_output=True, text=True, timeout=self.timeout, shell=False)
            except subprocess.TimeoutExpired as exc: raise DecodeError(f"DJI decoder timed out after {self.timeout}s") from exc
            log = proc.stdout + "\n" + proc.stderr
            if proc.returncode or not output.exists():
                if "create R-JPEG dirp handle failed" in log: raise UnsupportedThermalImage("No usable DJI radiometric payload or unsupported DJI format")
                raise DecodeError(f"DJI decoder failed (code {proc.returncode}): {log[-500:]}")
            match = re.search(r"image\s+width\s*:\s*(\d+).*?image height\s*:\s*(\d+)", log, re.S)
            if not match: raise DecodeError("DJI decoder did not report matrix dimensions")
            width, height = map(int, match.groups()); matrix = np.fromfile(output, dtype="<f4")
            if matrix.size != width * height: raise DecodeError("DJI output size does not match reported dimensions")
            matrix = matrix.reshape((height, width)); valid = np.isfinite(matrix)
            ranges = {}
            for key, label in [("distance","distance"),("humidity","humidity"),("emissivity","emissivity"),("atmospheric_temperature","ambientTemp"),("reflected_temperature","reflection")]:
                m = re.search(rf"{label}: \[([-\d.]+),([-\d.]+)\]", log)
                if m: ranges[key] = {"min":float(m.group(1)), "max":float(m.group(2))}
            provenance = {k:("user_override" if parameters.get(k) is not None else "image_or_sdk_default") for k in flags}
            return DecodeResult(None, self.version, width, height, matrix, valid, parameters, provenance, ranges, metadata={"decoder":"DJI dji_irp", "api_log":log[:2000]})

def image_signature(path: Path) -> str:
    head = path.read_bytes()[:12]
    if head[:3] == b"\xff\xd8\xff": return "jpeg"
    if head[:8] == b"\x89PNG\r\n\x1a\n": return "png"
    return "unknown"

def preview(source: Path, target: Path):
    try:
        with Image.open(source) as im:
            im.thumbnail((1600, 1200)); im.convert("RGB").save(target, "JPEG", quality=90)
    except UnidentifiedImageError as exc: raise DecodeError("Corrupt or unreadable image") from exc

def statistics(matrix: np.ndarray, mask: np.ndarray) -> dict:
    valid = mask & np.isfinite(matrix)
    if not valid.any(): raise DecodeError("Region contains no valid measurement pixels")
    indices = np.flatnonzero(valid); values = matrix.flat[indices]
    # np.argmin/argmax selects the first row-major occurrence: smallest y, then x.
    min_flat = int(indices[int(np.argmin(values))]); max_flat = int(indices[int(np.argmax(values))]); width = matrix.shape[1]
    return {"minimum_c":float(matrix.flat[min_flat]), "minimum_location":{"x":min_flat%width,"y":min_flat//width}, "maximum_c":float(matrix.flat[max_flat]), "maximum_location":{"x":max_flat%width,"y":max_flat//width}, "mean_c":float(values.mean(dtype=np.float64)), "valid_pixels":int(values.size)}

def region_mask(shape: tuple[int,int], kind: str, points: list[dict]) -> np.ndarray:
    import cv2
    mask = np.zeros(shape, np.uint8); pts = np.array([[p["x"],p["y"]] for p in points], np.int32)
    if kind == "rectangle":
        x1,y1 = pts[0]; x2,y2 = pts[1]; cv2.rectangle(mask,(min(x1,x2),min(y1,y2)),(max(x1,x2),max(y1,y2)),1,-1)
    elif kind == "circle":
        x1,y1 = pts[0]; x2,y2 = pts[1]; radius=max(1,int(round(((x2-x1)**2+(y2-y1)**2)**0.5))); cv2.circle(mask,(int(x1),int(y1)),radius,1,-1)
    else: cv2.fillPoly(mask,[pts],1)
    return mask.astype(bool)

def hotspots(matrix: np.ndarray, valid: np.ndarray, roi: np.ndarray, threshold: float, minimum_area: int) -> list[dict]:
    import cv2
    binary = (valid & roi & (matrix >= threshold)).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(binary, 8)
    found=[]
    for label in range(1,count):
        area=int(stats[label,cv2.CC_STAT_AREA])
        if area < minimum_area: continue
        component=labels==label; stat=statistics(matrix,component); contours,_=cv2.findContours(component.astype(np.uint8),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        outline=max(contours,key=cv2.contourArea).reshape(-1,2).tolist()
        found.append({"peak_c":stat["maximum_c"],"pixel_area":area,"location":stat["maximum_location"],"outline":outline})
    return sorted(found,key=lambda x:(-x["peak_c"],x["location"]["y"],x["location"]["x"]))
