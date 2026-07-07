# Exotic VLIW Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Explore and, if profitable, land one strict-correctness exotic optimization for the 1092-cycle VLIW kernel.

**Architecture:** Implement a default-off `PADDR_SPACE` prototype that carries deep-gather memory addresses directly through depths 5-10, replacing next-round gather address adds with previous-round address-space traversal. If it beats 1092 and passes verification, make it the default; otherwise remove the prototype and document the NO-GO.

**Tech Stack:** Python emitter in `perf_takehome.py`, project verification scripts, shell-driven benchmark probes.

---

### Task 1: Add PADDR-Space Prototype

**Files:**
- Modify: `perf_takehome.py`

- [ ] **Step 1: Add the feature flag**

Add this field in `KernelBuilder.__init__` after `_pspace` is initialized:

```python
self._paddr_space = int(_os.environ.get("PADDR_SPACE", "0"))
```

- [ ] **Step 2: Add setup constants**

In the p-space `fvp_p_d` setup block, keep `fvp_p_3`, `fvp_p_4`, and `fvp_p_5`, but skip `fvp_p_6..fvp_p_10` when `_paddr_space` is enabled. Add:

```python
if self._pspace and self._paddr_space:
    c["paddr_bias"] = self.broadcast_const("paddr_bias", (1 - FVP) % (2**32))
```

- [ ] **Step 3: Add direct address gather helper**

Add a helper near `_gather_node`:

```python
def _gather_node_addrready(self, node, idx_addr):
    for i in range(V):
        self.op("load", ("load", node + i, idx_addr + i),
                reads=(idx_addr + i,), writes=(node + i,))
```

- [ ] **Step 4: Extend `_emit_vec_round` signature**

Change the signature to:

```python
def _emit_vec_round(self, v, c, depth, j=0, skip_idx_update=False,
                    defer_k5=False, enter_x=False,
                    idx_is_paddr=False, paddr_next=False):
```

- [ ] **Step 5: Use direct gather for paddr rounds**

In the `depth >= 4` gather path, before the d4 mux/cold checks, use:

```python
if self._pspace and self._paddr_space and idx_is_paddr and depth >= 5:
    self._gather_node_addrready(node, idx)
```

Depth 4 stays on the existing p-space representation so the sparse `D4_COLD_MASK`
continues to work.

- [ ] **Step 6: Emit paddr traversal**

In the p-space traverse branch, before the existing defer/non-defer cases, add:

```python
if paddr_next:
    assert not defer_k5, "paddr-space prototype only covers non-defer deep rounds"
    if idx_is_paddr:
        self.v_alu("+", addr, addr, c["paddr_bias"])
        self.v_muladd(idx, idx, m2, addr)
    else:
        self.v_alu("+", addr, c[f"fvp_p_{depth + 1}"], addr)
        self.v_muladd(idx, idx, m2, addr)
```

The existing p-space traverse cases must be in the corresponding `else` block so
only one traversal is emitted.

- [ ] **Step 7: Pass paddr flags from `gen_body`**

At the `_emit_vec_round` call site, compute:

```python
cur_depth = r % h1
next_depth = (r + 1) % h1
idx_is_paddr = bool(self._paddr_space and self._pspace and cur_depth >= 5)
paddr_next = bool(self._paddr_space and self._pspace and
                  r != rounds - 1 and not skip and next_depth >= 5)
```

Pass both flags into `_emit_vec_round`.

### Task 2: Measure PADDR-Space

**Files:**
- No file edits expected.

- [ ] **Step 1: Run baseline**

Run:

```bash
python tests/submission_tests.py
```

Expected: `OK` and `CYCLES:  1092`.

- [ ] **Step 2: Run prototype**

Run:

```bash
PADDR_SPACE=1 python tests/submission_tests.py
```

Expected: `OK`. If cycles are below 1092, continue to Task 3. If cycles are 1092
or worse, continue to Task 4.

- [ ] **Step 3: Profile prototype**

Run:

```bash
PADDR_SPACE=1 python - <<'PY'
from collections import Counter
from perf_takehome import KernelBuilder
S={'load':2,'alu':12,'valu':6,'flow':1,'store':2}
kb=KernelBuilder(); kb.build_kernel(10,2047,256,16)
e=Counter()
for b in kb.instrs:
    for k,sl in b.items():
        if k!='debug': e[k]+=len(sl)
print('cycles', len(kb.instrs))
print('ops', dict(e))
print('floors', {k: e[k]/S[k] for k in S})
print('F', (8*e['valu']+e['alu'])/60)
PY
```

Expected: profile explains whether the win came from setup load removal, critical
path shortening, or neither.

### Task 3: Land If PADDR-Space Wins

**Files:**
- Modify: `perf_takehome.py`

- [ ] **Step 1: Make default on**

Change the default flag value to:

```python
self._paddr_space = int(_os.environ.get("PADDR_SPACE", "1"))
```

- [ ] **Step 2: Verify strict correctness**

Run:

```bash
python parity_check.py && python algebra_check_ported.py
python tests/submission_tests.py
PSPACE=0 python tests/submission_tests.py
git diff -- tests/ problem.py
```

Expected: all tests pass; `git diff -- tests/ problem.py` prints nothing.

- [ ] **Step 3: Commit the win**

Run:

```bash
git add perf_takehome.py
git commit -m "perf: carry deep gather addresses in p-space"
```

### Task 4: Revert And Document If PADDR-Space Fails

**Files:**
- Modify: `perf_takehome.py`
- Create: `directions/41-paddr-space-NOGO.md`

- [ ] **Step 1: Revert prototype code**

Remove all `PADDR_SPACE` changes from `perf_takehome.py` so the shipped kernel is
back to the original 1092-cycle implementation.

- [ ] **Step 2: Write NO-GO note**

Create `directions/41-paddr-space-NOGO.md` with:

```markdown
# PADDR-Space Deep Gather Address Carry — NO-GO

Baseline: 1092 cycles.

Hypothesis: carry deep-gather memory addresses directly for depths 5-10 so the
next gather does not need `addr = fvp_p_d + p` on its critical path.

Result:

```text
<paste PADDR_SPACE=1 cycle count and engine profile>
```

Verdict: NO-GO if realized cycles are not below 1092.

Reason: the address add is moved rather than deleted; the added paddr-bias
dependency and unchanged F/load floors do not improve the drain schedule enough
to beat the current W7-C 1092 graph.

Reproduce:

```bash
PADDR_SPACE=1 python tests/submission_tests.py
```
```

- [ ] **Step 3: Commit the NO-GO note**

Run:

```bash
git add directions/41-paddr-space-NOGO.md
git commit -m "docs: record paddr-space optimization result"
```

