"""Greedy coordinate descent over the combine mask under the 1225 offset
schedule, rot=31 oracle (guaranteed bound since rot=31 is argmin). Re-sweeps
after each accepted flip to capture interactions."""
import multiprocessing as mp, time
import perf_takehome as P
SHAPE=(10,2**11-1,256,16); K_VEC,ROUNDS=32,16; N_COMBINE=3*K_VEC*ROUNDS
OFF=[0,0,1,0,1,1,1,1,2,2,2,2,3,3,3,3,4,4,4,4,6,5,5,6,6,7,6,6,7,7,7,7]
def seed(): return [(gi<10 or gi>=N_COMBINE-100) for gi in range(N_COMBINE)]

_BASE=None
def _init(b):
    global _BASE; _BASE=b
def ev(m):
    kb=P.KernelBuilder(); kb._combine_mask=m; kb._pos_offset=OFF; kb._rotations=[31]
    kb.build_kernel(*SHAPE); return len(kb.instrs)
def _flip(i):
    m=list(_BASE); m[i]=not m[i]; return i, ev(m)

def full(m):
    kb=P.KernelBuilder(); kb._combine_mask=m; kb._pos_offset=OFF
    kb.build_kernel(*SHAPE); return len(kb.instrs)

if __name__=="__main__":
    base=seed()
    best=ev(base); print(f"start {best}")
    rnd=0
    while True:
        rnd+=1
        with mp.Pool(8, initializer=_init, initargs=(base,)) as p:
            res=p.map(_flip, range(N_COMBINE), chunksize=16)
        imp=sorted([(c,i) for i,c in res if c<best])
        print(f"[round {rnd}] best={best} improving={len(imp)}")
        if not imp: 
            print("converged"); break
        applied=0
        for c,i in imp:
            m=list(base); m[i]=not m[i]
            nc=ev(m)
            if nc<best:
                base=m; best=nc; applied+=1
        print(f"  applied {applied}, best={best}")
        if applied==0: break
    f=full(base)
    print(f"\nFINAL rot31={best}  FULL 32-rot build={f}")
    import json
    with open("champ_mask_offset.json","w") as fh:
        json.dump({"rot31":best,"full":f,"mask":[int(b) for b in base],"offsets":OFF}, fh)
    print("saved champ_mask_offset.json")
