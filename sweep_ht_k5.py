"""Re-sweep (head,tail) AND step on the K5-deferred graph, uniform diagonal
(no _pos_offset override), to find the new mask baseline. Full builds."""
import multiprocessing as mp, time
import perf_takehome as P
SHAPE=(10,2**11-1,256,16); K_VEC,ROUNDS=32,16; N=3*K_VEC*ROUNDS
def _b(args):
    head,tail,step=args
    kb=P.KernelBuilder()
    kb._pos_offset=[p//step for p in range(32)]  # uniform diagonal
    kb._combine_mask=[(gi<head or gi>=N-tail) for gi in range(N)]
    kb._step=step
    kb.build_kernel(*SHAPE)
    return (head,tail,step), len(kb.instrs)
if __name__=="__main__":
    grid=[(h,t,s) for h in (0,8,16,20,24,28,32) for t in (80,100,120,140,160) for s in (4,)]
    t0=time.time()
    with mp.Pool(8) as p: res=p.map(_b,grid)
    res.sort(key=lambda r:r[1])
    print(f"{len(grid)} K5-graph full builds in {time.time()-t0:.0f}s (uniform diagonal)\n")
    for (h,t,s),c in res[:15]:
        print(f"{c}  head={h} tail={t} step={s}")
    print(f"\nBEST {res[0][1]} at {res[0][0]}")
