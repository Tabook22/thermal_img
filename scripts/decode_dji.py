"""Minimal verified DJI SDK decoder. Requires numpy and DJI's licensed dji_irp utility."""
import argparse, json, re, subprocess, tempfile
from pathlib import Path
import numpy as np

p=argparse.ArgumentParser(); p.add_argument("image",type=Path); p.add_argument("--dji-irp",type=Path,required=True); args=p.parse_args()
with tempfile.TemporaryDirectory(prefix="dji-decode-") as d:
    raw=Path(d)/"temperature.raw"
    proc=subprocess.run([str(args.dji_irp),"-s",str(args.image),"-a","measure","-o",str(raw),"--measurefmt","float32"],cwd=args.dji_irp.parent,capture_output=True,text=True,shell=False,check=False)
    log=proc.stdout+proc.stderr
    if proc.returncode: raise SystemExit(log)
    m=re.search(r"image\s+width\s*:\s*(\d+).*?image height\s*:\s*(\d+)",log,re.S)
    if not m: raise SystemExit("SDK did not report dimensions")
    width,height=map(int,m.groups()); matrix=np.fromfile(raw,dtype="<f4").reshape(height,width); valid=np.isfinite(matrix); indices=np.flatnonzero(valid); vals=matrix.flat[indices]
    lo=int(indices[np.argmin(vals)]); hi=int(indices[np.argmax(vals)])
    print(json.dumps({"width":width,"height":height,"valid_pixels":int(valid.sum()),"minimum_c":float(matrix.flat[lo]),"minimum_xy":[lo%width,lo//width],"maximum_c":float(matrix.flat[hi]),"maximum_xy":[hi%width,hi//width],"mean_c":float(vals.mean(dtype=np.float64))},indent=2))

