"""Offset search on the K5-deferred graph. Default KernelBuilder now ships
head/tail=24/100 + uniform diagonal (1215). We search _pos_offset only; the
combine mask is left at the shipped head/tail default (so _combine_mask=None ->
the build applies 24/100). rot=31 oracle (verify argmin below)."""
import multiprocessing as mp, random, time, json
import perf_takehome as P
SHAPE=(10,2**11-1,256,16); K_VEC,ROUNDS=32,16; K=K_VEC

def build(off, rot):
    kb=P.KernelBuilder()
    kb._pos_offset=off
    kb._rotations=[rot] if rot is not None else None
    kb.build_kernel(*SHAPE)
    return len(kb.instrs)

ROTS=[0, 1, 30, 31, 22, 29]
def proxy(off):
    # full min-over-32 is the true shipped objective; offsets shift the argmin
    # unpredictably, so screen on the true min rather than a fixed rot subset.
    return build(off, None)
def _job(a):
    i,off=a; return i, proxy(off), off

def neighbor(off,rng,strength):
    o=list(off)
    for _ in range(rng.randint(1,strength)):
        p=rng.randrange(K); o[p]=max(0,o[p]+rng.choice((-1,1)))
    return o

def main():
    rng=random.Random(4242)
    best=[p//4 for p in range(K)]
    t0=time.time()
    best_proxy=proxy(best); best_full=build(best,None)
    print(f"uniform diagonal: proxy={best_proxy} full={best_full} ({time.time()-t0:.0f}s)")
    inc=best; inc_p=best_proxy
    rounds=16; batch=24
    with mp.Pool(8) as pool:
        for rnd in range(rounds):
            strength=1+(rnd%3)
            cands=[neighbor(inc,rng,strength) for _ in range(batch)]
            cands+= [[rng.randint(0,9) for _ in range(K)] for _ in range(batch//4)]
            res=pool.map(_job,[(i,c) for i,c in enumerate(cands)])
            res.sort(key=lambda r:r[1])
            bi,bp,bo=res[0]
            if bp<inc_p or (bp==inc_p and rng.random()<0.4):
                inc,inc_p=bo,bp
            note=""
            if bp<best_full:
                best_full,best,best_proxy=bp,bo,bp; note=f"  <== NEW BEST full={bp}"
            print(f"[r{rnd:2d} s{strength}] bproxy={bp} inc={inc_p} best_full={best_full}{note}")
    print(f"\nBEST full={best_full}\noffsets={best}")
    with open("best_offsets_k5.json","w") as fh: json.dump({"full":best_full,"offsets":best},fh)

if __name__=="__main__": main()
