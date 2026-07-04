"""Single-bit combine sweep at rot=31 UNDER the 1225 offset schedule. Tests
whether the reshaped drain opened new mask headroom."""
import multiprocessing as mp, time
import perf_takehome as P
SHAPE=(10,2**11-1,256,16); K_VEC,ROUNDS=32,16; N_COMBINE=3*K_VEC*ROUNDS
OFF=[0,0,1,0,1,1,1,1,2,2,2,2,3,3,3,3,4,4,4,4,6,5,5,6,6,7,6,6,7,7,7,7]
def seed(): return [(gi<10 or gi>=N_COMBINE-100) for gi in range(N_COMBINE)]
BASE=seed()
def ev(m):
    kb=P.KernelBuilder(); kb._combine_mask=m; kb._pos_offset=OFF; kb._rotations=[31]
    kb.build_kernel(*SHAPE); return len(kb.instrs)
def _flip(i):
    m=list(BASE); m[i]=not m[i]; return i, ev(m)
if __name__=="__main__":
    b=ev(BASE); print(f"base rot31 under offsets: {b}")
    t0=time.time()
    with mp.Pool(8) as p: res=p.map(_flip, range(N_COMBINE), chunksize=16)
    imp=sorted([(c,i) for i,c in res if c<b])
    print(f"swept {N_COMBINE} in {time.time()-t0:.0f}s; improving={len(imp)}")
    for c,i in imp[:20]: print(f"  bit {i} -> {c} (delta {c-b})")
    if not imp: print("ZERO improving flips -- mask saturated under offsets too")
