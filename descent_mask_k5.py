"""After the offset search converges, co-optimize the combine mask under the
best offsets on the K5 graph. Single-bit coordinate descent using the true
full-32-rot objective (argmin rotation is unstable under K5, so no single-rot
shortcut). Seeded from best_offsets_k5b.json (or the shipped champion)."""
import json, multiprocessing as mp, os, time
import perf_takehome as P
SHAPE=(10,2**11-1,256,16); K_VEC,ROUNDS=32,16; N=3*K_VEC*ROUNDS

def load_off():
    for fn in ("best_offsets_k5b.json","best_offsets_k5.json"):
        if os.path.exists(fn):
            return json.load(open(fn))["offsets"]
    return [6,5,2,9,8,0,1,8,7,1,8,3,5,3,3,9,9,7,3,2,5,6,5,4,3,1,7,8,9,1,0,1]

OFF=load_off()
def base_mask():
    return [(gi<24 or gi>=N-100) for gi in range(N)]

_BASE=None
def _init(b):
    global _BASE; _BASE=b
def full(m):
    kb=P.KernelBuilder(); kb._combine_mask=m; kb._pos_offset=OFF
    kb.build_kernel(*SHAPE); return len(kb.instrs)
def _flip(i):
    m=list(_BASE); m[i]=not m[i]; return i, full(m)

if __name__=="__main__":
    base=base_mask(); best=full(base)
    print(f"offsets={OFF}\nbase mask(24/100) full={best}")
    rnd=0
    while True:
        rnd+=1
        t0=time.time()
        with mp.Pool(8, initializer=_init, initargs=(base,)) as p:
            res=p.map(_flip, range(N), chunksize=16)
        imp=sorted([(c,i) for i,c in res if c<best])
        print(f"[round {rnd}] best={best} improving={len(imp)} ({time.time()-t0:.0f}s)")
        if not imp: print("converged"); break
        applied=0
        for c,i in imp:
            m=list(base); m[i]=not m[i]; nc=full(m)
            if nc<best: base=m; best=nc; applied+=1
        print(f"  applied {applied}, best={best}")
        if applied==0: break
    print(f"\nFINAL full={best}")
    extra=[i for i in range(N) if base[i]!=base_mask()[i]]
    print(f"mask diff from 24/100: {extra}")
    json.dump({"full":best,"offsets":OFF,"mask":[int(b) for b in base]},
              open("champ_k5_final.json","w"))
