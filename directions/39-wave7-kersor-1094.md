# Wave-7 KerSor Worktree Plan @ 1094

> **For agentic workers:** start from a fresh worktree created by
> `scripts/setup-wave7-kersor-worktrees.sh`. Read this document, then run KerSor
> with `kersor/kersor-spec.md`. Do not modify `tests/` or `problem.py`.

**Goal:** beat the verified 1094-cycle VLIW kernel, with a long-shot target of
sub-1000 cycles.

**Baseline:** `explore/wave6-1111` plus Wave-7 seed changes:

- `B0_CARRY=1` default.
- `D3_GATHER_MASK = {0,1,37}`.
- `D4_COLD_MASK = {6,7,9,16,21,23,24,25,29,32,35}`.
- `_POS_OFFSET_PSPACE_32x16 = [3,4,1,10,7,3,1,10,6,2,7,10,5,4,2,6,10,8,4,5,4,3,5,4,7,4,6,9,8,0,1,0]`.

Verified commands:

```bash
python tests/submission_tests.py              # OK, CYCLES: 1094
PSPACE=0 python tests/submission_tests.py     # OK, CYCLES: 1184
python parity_check.py && python algebra_check_ported.py
git diff -- tests/                            # must stay empty
```

## Current Engine Profile

Measured on `forest_height=10, n_nodes=2047, batch_size=256, rounds=16`:

```text
load  2071 ops / 2  = 1035.5
valu  6189 ops / 6  = 1031.5
F = (8*valu + alu)/60 = 1025.1
alu  11992 ops / 12 =  999.3
flow   859 ops / 1  =  859.0
realized = 1094, tail over max floor ~= 58.5 cycles
```

Interpretation:

- This graph is no longer pure load-bound. Load, valu, and F are close enough
  that any single-axis shuffle is likely to be absorbed.
- The wrong-output `GATHER_FREE=1` probe schedules at 993, so sub-1000 is not
  impossible for the scheduler, but only if node fetch work is replaced by a
  correctness-preserving representation.
- Free deletion probes are sobering: skipping all d5-d10 gathers still lands
  around 1071 unless the rest of the graph is retuned. A real deep-gather
  replacement must be cheaper than prior d4/d5 tournament attempts and must
  avoid hot node/addr pooling.

## Worktree Lanes

Each lane owns one branch and one narrow question. A lane should commit either
one verified win or one NO-GO document with reproducible commands.

### W7-A: Deep Gather Representation

**Branch:** `explore/w7-a-deep-gather`

**Question:** can any correctness-preserving representation for depth >= 5 cut
scalar gather load without paying more than it saves?

**Allowed files:**

- Modify: `perf_takehome.py`
- Create: `experiments/probe_w7_deep_gather.py`
- Create if killed: `directions/40-w7-deep-gather-NOGO.md`

**Starting facts:**

- `GATHER_FREE=1` is wrong-output only; it is a lower-bound probe, not a valid
  optimization.
- Prior d4 resident-table path failed because 128 words forced node/addr pooling.
- D5 full mux is dominated by d4: 32-way select cost is too high for the same
  eight-load saving per converted instance.
- Current scratch free is only 21 words with the default d4 cold table enabled.

**Required first probe:**

```bash
python - <<'PY'
from collections import Counter
import perf_takehome as P
S={'load':2,'alu':12,'valu':6,'flow':1,'store':2}
SHAPE=(10,2047,256,16)
orig=P.KernelBuilder._gather_node
def prof(label):
    kb=P.KernelBuilder(); kb.build_kernel(*SHAPE)
    eng=Counter()
    for b in kb.instrs:
        for e,slots in b.items(): eng[e]+=len(slots)
    f={e:eng[e]/S[e] for e in S}; f['F']=(8*eng['valu']+eng['alu'])/60
    print(label, len(kb.instrs), f, dict(eng))
for ds in [{5},{6},{7},{5,6},{5,6,7,8,9,10}]:
    def skip(self,node,addr,idx,c,depth,ds=ds):
        if depth in ds: return
        return orig(self,node,addr,idx,c,depth)
    P.KernelBuilder._gather_node=skip
    prof('skip'+','.join(map(str,sorted(ds))))
P.KernelBuilder._gather_node=orig
PY
```

**Kill criteria:**

- Kill if the modeled replacement adds more than 16 flow ops or 24 valu ops per
  converted deep-gather instance.
- Kill if it requires persistent tables larger than the available 21 scratch
  words, unless the table uses only setup-dead scratch already recycled before
  the body.
- Kill if a bit-exact prototype cannot beat 1094 after a local offset retune.

**Win gate:**

```bash
python parity_check.py && python algebra_check_ported.py
python tests/submission_tests.py              # must print CYCLES < 1094
PSPACE=0 python tests/submission_tests.py     # must stay <= 1184
git diff -- tests/                            # must be empty
```

### W7-B: Traverse/Hash Structural Deletion

**Branch:** `explore/w7-b-traverse-structure`

**Question:** is there any remaining redundant traverse or hash computation that
can be eliminated, not merely moved between engines?

**Allowed files:**

- Modify: `perf_takehome.py`
- Create: `experiments/probe_w7_traverse_structure.py`
- Create if killed: `directions/41-w7-traverse-structure-NOGO.md`

**Starting facts:**

- B0 carry is already landed and default-on.
- The old 320-entry extract mask now covers all extract instances in the 1094
  graph; there is no uncovered D4 extract class left to migrate.
- Remaining `hi=(1<p)` and `b1/b2` extracts require either recomputation or a
  carried value. Any carried value must be scratch-free or must reuse an already
  live per-vector register without extending hot live ranges.
- Hash stages s1 and s5 are xorshift-like and previously proved irreducible;
  reopen only with a concrete algebraic identity and a random equivalence check.

**Required first probe:**

Instrument a monkeypatch that deletes the candidate op class while preserving
the scheduler shape enough to measure its maximum possible cycle impact. If the
wrong-output free-delete bound is not below 1094 by at least 10 cycles, kill the
candidate before implementing it.

**Algebra gate for any hash rewrite:**

```bash
python - <<'PY'
import random
from problem import myhash
def candidate(x):
    # replace with the proposed pure-Python candidate expression
    return myhash(x)
for n in [0,1,2,3,4,5,0xffffffff,0x80000000,0x7fffffff]:
    assert candidate(n) == myhash(n), hex(n)
for _ in range(1_000_000):
    x=random.randrange(2**32)
    assert candidate(x) == myhash(x), hex(x)
print('candidate hash identity: PASS')
PY
```

**Win gate:** same as W7-A.

### W7-C: Multi-Rot Tail And Mask Retune

**Branch:** `explore/w7-c-tail-retune`

**Question:** can the 58-cycle tail over the current max floor be reduced by a
fresh search over offsets, d3/d4 masks, and engine masks using rot29-aware
objectives?

**Allowed files:**

- Modify: `perf_takehome.py`
- Modify: `experiments/anneal_pos_offset.py`
- Modify or create: `experiments/anneal_w7_joint.py`
- Create if killed: `directions/42-w7-tail-retune-NOGO.md`

**Starting facts:**

- Current best rotation is 29. A rot27-only oracle is stale.
- Single-bit `CONST_FLOW_MASK` flips mostly tie at 1094; do not spend a full
  KerSor round on const-only search.
- A short rot29 offset search found 1094 from 1097. Expect small wins only unless
  paired with a real structural cut.

**Required objective:**

- Oracle must evaluate at least rotations `{25,27,29}`.
- Full confirmation must evaluate all 32 rotations.
- A candidate is shippable only when full-32 cycles are below 1094.

**Seed offset:**

```python
[3,4,1,10,7,3,1,10,6,2,7,10,5,4,2,6,10,8,4,5,4,3,5,4,7,4,6,9,8,0,1,0]
```

**Win gate:** same as W7-A.

### W7-D: Scheduler Objective / Search Infrastructure

**Branch:** `explore/w7-d-scheduler-objective`

**Question:** can faster, more reliable search infrastructure expose wins that
manual single-rot SA misses?

**Allowed files:**

- Modify: `experiments/omni_anneal.py`
- Modify: `experiments/anneal_d3d4_joint.py`
- Create: `experiments/w7_oracle.py`
- Create if useful: `directions/43-w7-search-infra.md`

**Required deliverable:**

Create a reusable evaluator with:

- `build_full(genome) -> cycles`
- `build_rots(genome, rots=(25,27,29)) -> min_cycles`
- engine-floor reporting: load, alu, valu, flow, F, tail
- JSON output for every confirmed candidate

**Kill criteria:**

- Kill if the evaluator does not reproduce baseline 1094 exactly.
- Kill if it cannot complete 100 rot-window evaluations in under 10 minutes on
  the local machine.

**This lane may land infrastructure without a cycle win** only if it is used by
one of the other Wave-7 lanes in the same branch series. Otherwise keep it as a
NO-GO/infrastructure note, not a default-code change.

## KerSor Invocation

After creating a lane worktree:

```bash
cd /path/to/vliw-w7-a-deep-gather
python tests/submission_tests.py
PSPACE=0 python tests/submission_tests.py
/kersor:optimize ./kersor \
  --spec kersor/kersor-spec.md \
  --mode explore \
  --yolo \
  --allow-workflow-evolution \
  --allow-workflow-authoring \
  --workflow-evolution-budget 10 \
  --workflow-authoring-budget 4 \
  --max-workflows 24 \
  --note "Wave-7 @1094. Read directions/39-wave7-kersor-1094.md. Work only on this lane. Do not use CUDA workflows. Do not modify tests/ or problem.py."
```

## Commit Rules

Each lane commit must include:

```bash
python parity_check.py && python algebra_check_ported.py
python tests/submission_tests.py
PSPACE=0 python tests/submission_tests.py
git diff -- tests/
```

Commit message format:

```text
perf(w7): <lane> <old cycles> -> <new cycles>
```

For a NO-GO:

```text
docs(w7): <lane> NO-GO @1094
```
