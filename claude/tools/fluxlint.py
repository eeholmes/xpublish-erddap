"""Minimal ERDDAP-readiness linter for a Flux DAP2 group."""
import re, sys, subprocess, datetime as dt
import numpy as np

def fetch(url):
    r = subprocess.run(["curl","-gsS","--max-time","120",url],capture_output=True)
    if r.returncode: raise RuntimeError(r.stderr.decode()[:200])
    return r.stdout

def main(base):
    dds = fetch(base+".dds").decode("utf-8","replace")
    das = fetch(base+".das").decode("utf-8","replace")
    print(f"### {base}")
    print(f"  .dds {len(dds)}B   .das {len(das)}B")

    # dimension signatures
    sigs={}
    arrays = re.findall(r"Array:\s*\n\s+(Float\d+|Int\d+|Byte|String) (\w+)(\[[^;]*\]);", dds)
    for m in [type("M",(),{"group":lambda s,i,a=a: a[i-1]})() for a in arrays]:
        var, dims = m.group(2), re.sub(r"\s*=\s*\d+","",m.group(3))
        sigs.setdefault(dims,[]).append(var)
    # drop pure axis declarations (1-D whose name == its dim)
    grids={k:[v for v in vs] for k,vs in sigs.items()}
    print("\n  -- dimension signatures (ERDDAP needs ONE per dataset) --")
    for k,vs in sorted(grids.items(), key=lambda x:-len(x[1])):
        print(f"   {len(vs):4d}  {k}   e.g. {', '.join(vs[:3])}")
    n_ds = len([k for k,vs in grids.items() if len(k.split('][')) > 1])
    print(f"   => BLOCKER if >1 multi-dim signature. distinct multi-dim sigs: {n_ds}")

    # axes: monotonicity
    print("\n  -- axis monotonicity --")
    top = dds.split("Grid {")[0]
    axes = list(dict.fromkeys(re.findall(r"^\s+(Float\d+|Int\d+) (\w+)\[\2 = (\d+)\];", top, re.M)))
    for _typ, name, n in axes:
        try:
            raw = fetch(f"{base}.dods?{name}")
            i = raw.find(b"Data:\n"); body = raw[i+6:]
            cnt = int(np.frombuffer(body[:4],dtype=">i4")[0])
            code = {"Float64":">f8","Float32":">f4","Int32":">i4","Int16":">i2"}[_typ]
            v = np.frombuffer(body[8:8+cnt*np.dtype(code).itemsize],dtype=code)
            d = np.diff(v.astype("f8")); uniq=len(np.unique(v))
            ok = bool((d>0).all()) or bool((d<0).all())
            flag = "OK " if ok else "FAIL"
            print(f"   [{flag}] {name:8s} n={cnt:6d} unique={uniq:6d} "
                  f"asc={bool((d>0).all())} dup={cnt-uniq} "
                  f"range=[{v.min():.4g},{v.max():.4g}]")
            if not ok:
                bad=np.where(d<=0)[0]
                print(f"          first break at i={bad[0]}: {v[bad[0]]} -> {v[bad[0]+1]}")
        except Exception as e:
            print(f"   [ERR ] {name}: {type(e).__name__} {e}")

    # DAS hazards
    print("\n  -- DAS hazards --")
    nans = re.findall(r"^\s+\w+ (\w+) (nan|-?inf\w*);", das, re.M|re.I)
    print(f"   bare nan/inf attribute literals: {len(nans)}"
          + (f"  {sorted(set(a for a,_ in nans))}" if nans else ""))

    # ACDD
    g = re.search(r"NC_GLOBAL \{(.*?)\n    \}", das, re.S)
    gtxt = g.group(1) if g else ""
    req = ["title","summary","institution","infoUrl","license","Conventions","cdm_data_type"]
    missing=[a for a in req if not re.search(rf'\b{a}\b\s',gtxt)]
    print(f"   NC_GLOBAL present: {bool(g)}")
    print(f"   missing required ACDD globals: {missing or 'none'}")
    nvar = len(re.findall(r"\n    (\w+) \{", das)) - 1
    ioos = len(re.findall(r"ioos_category", das))
    print(f"   variables in DAS: ~{nvar};  with ioos_category: {ioos}")

for b in sys.argv[1:]: main(b); print()
