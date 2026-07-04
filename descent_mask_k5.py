"""Mask coordinate descent under the fixed 1208 offset schedule (K5 graph).
Oracle = rot=28 (the measured argmin under these offsets, gap to next is 8),
so single-rot count is a fast valid bound; the final champion is confirmed on
the full 32-rot build. alu is the binding engine at 1208, so alu->valu flips
(head/tail interior) are the promising direction."""
import json, multiprocessing as mp, os, time
import perf_takehome as P
SHAPE=(10,2**11-1,256,16); N=3*32*16
OFF=[6,5,2,9,8,0,1,8,7,1,8,3,5,3,3,9,9,7,3,2,5,6,5,4,3,1,7,8,9,1,0,1]
AROT=28

def base_mask(): return [(gi<24 or gi>=N-100) for gi in range(N)]
_BASE=None
def _init(b):
    global _BASE; _BASE=b
def ev(m, rot=AROT):
    kb=P.KernelBuilder(); kb._combine_mask=m; kb._pos_offset=OFF
    kb._rotations=[rot] if rot is not None else None
    kb.build_kernel(*SHAPE); return len(kb.instrs)
def _flip(i):
    m=list(_BASE); m[i]=not m[i]; return i, ev(m)

if __name__=="__main__":
    base=base_mask(); best=ev(base)
    fullb=ev(base, None)
    print(f"base 24/100 rot{AROT}={best} full={fullb}", flush=True)
    rnd=0
    while True:
        rnd+=1; t0=time.time()
        with mp.Pool(8, initializer=_init, initargs=(base,)) as p:
            res=p.map(_flip, range(N), chunksize=16)
        imp=sorted([(c,i) for i,c in res if c<best])
        print(f"[round {rnd}] rot{AROT}best={best} improving={len(imp)} ({time.time()-t0:.0f}s)", flush=True)
        if not imp: print("converged", flush=True); break
        applied=0
        for c,i in imp:
            m=list(base); m[i]=not m[i]; nc=ev(m)
            if nc<best: base=m; best=nc; applied+=1
        print(f"  applied {applied}, rot{AROT}best={best}", flush=True)
        if applied==0: break
    full=ev(base, None)
    print(f"\nFINAL rot{AROT}={best} FULL32={full}", flush=True)
    extra=[i for i in range(N) if base[i]!=base_mask()[i]]
    print(f"mask diff from 24/100: {extra}")
    json.dump({"rot28":best,"full":full,"offsets":OFF,"mask":[int(b) for b in base]},
              open("champ_k5_final.json","w"))
