"""Fast offset search on the K5 graph. Proxy = min over a small rotation set
(the K5 argmins), which is ~8x cheaper than full-32; periodic full-build
re-rank of the incumbent. Writes progress to a flushed log + saves best JSON
every improvement so nothing is lost on interrupt."""
import json, multiprocessing as mp, random, sys, time
import perf_takehome as P
SHAPE=(10,2**11-1,256,16); K=32
CHAMP=[6, 5, 2, 9, 8, 0, 1, 8, 7, 1, 8, 3, 5, 3, 3, 9, 9, 7, 3, 2, 5, 6, 5, 4, 3, 1, 7, 8, 9, 1, 0, 1]
PROXY_ROTS=[0,1,30,31]

def build(off, rot):
    kb=P.KernelBuilder(); kb._pos_offset=off
    kb._rotations=[rot] if rot is not None else None
    kb.build_kernel(*SHAPE); return len(kb.instrs)
def proxy(off):
    # offsets scramble the argmin rotation unpredictably (measured: the 1208
    # champion's argmin is rot=28, not in any fixed subset), so a rotation
    # subset is an unreliable proxy. Use the true full-32 objective.
    return build(off, None)
def _job(a):
    i,off=a; return i, proxy(off), off
def neighbor(off,rng,strength):
    o=list(off)
    for _ in range(rng.randint(1,strength)):
        p=rng.randrange(K); o[p]=max(0,min(12,o[p]+rng.choice((-1,1))))
    return o
def log(m):
    print(m); sys.stdout.flush()
def save(off, full):
    json.dump({"full":full,"offsets":off}, open("best_offsets_k5b.json","w"))

def main():
    rng=random.Random(31337)
    best=list(CHAMP)
    best_full=build(best,None)
    best_proxy=proxy(best)
    log(f"seed champ: proxy={best_proxy} full={best_full}")
    save(best, best_full)
    inc=best; inc_p=best_proxy; stale=0
    rounds=30; batch=24
    with mp.Pool(8) as pool:
        for rnd in range(rounds):
            strength=1+(rnd%4)
            cands=[neighbor(inc,rng,strength) for _ in range(batch)]
            if stale>=5:
                cands+=[[rng.randint(0,10) for _ in range(K)] for _ in range(6)]; stale=0
            res=pool.map(_job,[(i,c) for i,c in enumerate(cands)])
            res.sort(key=lambda r:r[1])
            bi,bp,bo=res[0]
            if bp<inc_p or (bp==inc_p and rng.random()<0.5): inc,inc_p=bo,bp
            note=""
            if bp<best_full:  # proxy IS the full build now
                best_full,best,best_proxy=bp,bo,bp; note=f"  <== NEW BEST full={bp}"; stale=0
                save(best,best_full)
            else: stale+=1
            log(f"[r{rnd:2d} s{strength}] proxy={bp} inc={inc_p} best_full={best_full}{note}")
    log(f"\nBEST full={best_full}\noffsets={best}")
    save(best,best_full)

if __name__=="__main__": main()
