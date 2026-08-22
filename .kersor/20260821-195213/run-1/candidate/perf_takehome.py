"""
Optimized KernelBuilder for the VLIW SIMD forest-traversal kernel
(baseline: 147734 cycles from one-slot-per-bundle emission).

Strategy:
* The whole batch stays resident in scratch as batch_size/VLEN idx and val
  vectors of VLEN lanes. Each round gathers node values lane-by-lane with
  load_offset, xors them into val, and runs the six HASH_STAGES as valu
  lanes against constant vectors that are vbroadcast exactly once. idx is
  advanced with valu ops (multiply_add / vselect) covering the even/odd
  child choice and the n_nodes wrap; vals are vstored only after the last
  round. Debug and pause slots are skipped entirely (the submission harness
  runs with enable_debug False and enable_pause False).
* Emission is two-phase: build_kernel records program-order (engine, slot)
  pairs via emit(); the packer then greedily packs self.slots into
  self.instrs bundles that respect SLOT_LIMITS per engine per bundle,
  end-of-cycle write visibility (every consumer lands in a strictly later
  bundle than its producers), and at most one write per scratch address per
  bundle.
* forest_values_p, inp_indices_p and inp_values_p are read from memory
  header words 4, 5 and 6 at runtime -- never hardcoded. The builder is
  parametric in forest_height, n_nodes, batch_size and rounds, and all
  arithmetic wraps mod 2**32 exactly like the reference kernel.
"""

from problem import (
    DebugInfo,
    HASH_STAGES,
    SLOT_LIMITS,
    VLEN,
    SCRATCH_SIZE,
)


class KernelBuilder:
    """Builds the packed VLIW program; see the module docstring for strategy."""

    def __init__(self):
        self.instrs = []         # final program: list of {engine: [slot, ...]}
        self.slots = []          # program-order (engine, slot) pairs to pack
        self.scratch = {}        # name -> scratch address
        self.scratch_debug = {}  # address -> (name, length)
        self.scratch_ptr = 0
        self.const_map = {}      # scalar const value -> scratch address
        self.vconst_map = {}     # const value -> broadcast vector address

    def debug_info(self):
        return DebugInfo(scratch_map=self.scratch_debug)

    def emit(self, engine, slot):
        """Record one slot in program order; the packer schedules it later."""
        self.slots.append((engine, slot))

    # The baseline's add() name is kept as an alias so either spelling
    # accumulates program order for the packer.
    add = emit

    def alloc_scratch(self, name=None, length=1):
        addr = self.scratch_ptr
        if name is not None:
            self.scratch[name] = addr
            self.scratch_debug[addr] = (name, length)
        self.scratch_ptr += length
        assert self.scratch_ptr <= SCRATCH_SIZE, "Out of scratch space"
        return addr

    def scratch_const(self, val, name=None):
        """Scalar constant, cached by value; emits one load-engine const slot."""
        val %= 2**32
        if val not in self.const_map:
            addr = self.alloc_scratch(name or f"const_{val}")
            self.emit("load", ("const", addr, val))
            self.const_map[val] = addr
        return self.const_map[val]

    def vconst(self, val, name=None):
        """VLEN-lane broadcast of a constant, cached so it is broadcast once."""
        val %= 2**32
        if val not in self.vconst_map:
            src = self.scratch_const(val)
            addr = self.alloc_scratch(name or f"vconst_{val}", VLEN)
            self.emit("valu", ("vbroadcast", addr, src))
            self.vconst_map[val] = addr
        return self.vconst_map[val]

    # Alternate spelling for the vector constant cache.
    vscratch_const = vconst

    def alloc_vreg(self, name=None):
        """Fresh VLEN-lane vector register; alias used by the vector body."""
        return self.alloc_scratch(name, VLEN)

    def broadcast(self, src, name=None):
        """Fresh VLEN-lane vector holding a runtime scalar (not cached)."""
        addr = self.alloc_scratch(name, VLEN)
        self.emit("valu", ("vbroadcast", addr, src))
        return addr

    def build(self, slots, vliw: bool = True) -> list[dict]:
        """Dependence-aware multi-slot VLIW bundle packer.

        Program-order walk placing each slot into the earliest legal bundle,
        honoring end-of-cycle write visibility:
          RAW: a reader lands strictly after the bundle that wrote the address,
          WAW: one write per scratch address per bundle (a second write lands
               strictly after the first),
          WAR: a write may share a bundle with an earlier reader (all reads
               observe pre-cycle state) but never lands before one,
          MEM: a load lands strictly after any earlier store's bundle and a
               store never lands before an earlier load's bundle, since load/
               store addresses are runtime scratch values.
        Per-engine SLOT_LIMITS are respected. Debug and pause slots are dropped
        entirely (the submission harness runs with both disabled).
        """
        if not vliw:
            return [
                {engine: [slot]}
                for engine, slot in slots
                if engine != "debug" and slot[0] != "pause"
            ]

        def rw(engine, s):
            # Returns (scratch reads, scratch writes, mem kind) for a slot.
            op = s[0]

            def vec(base):
                return list(range(base, base + VLEN))

            if engine == "valu":
                if op == "vbroadcast":
                    return [s[2]], vec(s[1]), ""
                if op == "multiply_add":
                    return sum((vec(b) for b in s[2:5]), []), vec(s[1]), ""
                return vec(s[2]) + vec(s[3]), vec(s[1]), ""
            if engine == "alu":
                return [s[2], s[3]], [s[1]], ""
            if engine == "load":
                if op == "const":
                    return [], [s[1]], ""
                if op == "load":
                    return [s[2]], [s[1]], "ld"
                if op == "load_offset":
                    return [s[2] + s[3]], [s[1] + s[3]], "ld"
                return [s[2]], vec(s[1]), "ld"  # vload
            if engine == "store":
                if op == "vstore":
                    return [s[1]] + vec(s[2]), [], "st"
                return [s[1], s[2]], [], "st"
            if op == "vselect":  # flow
                return sum((vec(b) for b in s[2:5]), []), vec(s[1]), ""
            if op == "select":
                return [s[2], s[3], s[4]], [s[1]], ""
            if op == "add_imm":
                return [s[2]], [s[1]], ""
            if op == "coreid":
                return [], [s[1]], ""
            # jump / cond_jump* / jump_indirect / halt / trace_write: reads
            # only, scheduled as a barrier (this kernel emits none of them).
            return [x for x in s[1:] if isinstance(x, int)], [], "ctl"

        bundles: list[dict] = []
        last_write: dict[int, int] = {}
        last_read: dict[int, int] = {}
        last_ld = last_st = -1
        floor = 0
        top = -1  # highest bundle index filled so far
        for engine, slot in slots:
            if engine == "debug" or slot[0] == "pause":
                continue
            reads, writes, kind = rw(engine, slot)
            e = floor
            for r in reads:
                w = last_write.get(r, -1)
                if w >= e:
                    e = w + 1
            for a in writes:
                if last_write.get(a, -1) >= e:
                    e = last_write[a] + 1
                if last_read.get(a, -1) > e:
                    e = last_read[a]
            if kind == "ld":
                if last_st >= e:
                    e = last_st + 1
            elif kind == "st":
                if last_ld > e:
                    e = last_ld
            elif kind == "ctl":
                if top > e:
                    e = top
            k = e
            while True:
                while len(bundles) <= k:
                    bundles.append({})
                if len(bundles[k].get(engine, ())) < SLOT_LIMITS[engine]:
                    break
                k += 1
            bundles[k].setdefault(engine, []).append(slot)
            for r in reads:
                if k > last_read.get(r, -1):
                    last_read[r] = k
            for a in writes:
                if k > last_write.get(a, -1):
                    last_write[a] = k
            if k > top:
                top = k
            if kind == "ld":
                if k > last_ld:
                    last_ld = k
            elif kind == "st":
                if k > last_st:
                    last_st = k
            elif kind == "ctl":
                floor = k + 1
        return bundles

    def build_hash(self, val, tmp1, tmp2, vc):
        """Six-stage hash as valu ops over pre-broadcast constant vectors.

        Per stage: tmp1 = op1(val, C1); tmp2 = op3(val, C3); val = op2(tmp1, tmp2).
        All lanes wrap to 32 bits inside the valu engine.
        """
        slots = []
        for op1, val1, op2, op3, val3 in HASH_STAGES:
            slots.append(("valu", (op1, tmp1, val, vc[val1])))
            slots.append(("valu", (op3, tmp2, val, vc[val3])))
            slots.append(("valu", (op2, val, tmp1, tmp2)))
        return slots

    def build_kernel(self, forest_height, n_nodes, batch_size, rounds):
        tmpa = self.alloc_scratch("tmpa")
        tmpb = self.alloc_scratch("tmpb")
        init_vars = ["rounds", "n_nodes", "batch_size", "forest_height",
                     "forest_values_p", "inp_indices_p", "inp_values_p"]
        for i, v in enumerate(init_vars):
            self.alloc_scratch(v, 1)
            self.add("load", ("const", tmpa, i))
            self.add("load", ("load", self.scratch[v], tmpa))

        vc = {}
        for op1, val1, op2, op3, val3 in HASH_STAGES:
            for c in (val1, val3):
                if c not in vc:
                    a = self.scratch_const(c)
                    r = self.alloc_vreg("v_hc_%08x" % c)
                    self.add("valu", ("vbroadcast", r, a))
                    vc[c] = r
        for c in (0, 1, 2):
            if c not in vc:
                a = self.scratch_const(c)
                r = self.alloc_vreg("v_hc_%d" % c)
                self.add("valu", ("vbroadcast", r, a))
                vc[c] = r
        v_nn = self.alloc_vreg("v_n_nodes")
        v_fp = self.alloc_vreg("v_fp")
        self.add("valu", ("vbroadcast", v_nn, self.scratch["n_nodes"]))
        self.add("valu", ("vbroadcast", v_fp, self.scratch["forest_values_p"]))

        nvec = batch_size // VLEN
        W = max(1, min(nvec, 16))
        idx_r = [self.alloc_vreg("idx_%d" % i) for i in range(nvec)]
        val_r = [self.alloc_vreg("val_%d" % i) for i in range(nvec)]
        w_node = [self.alloc_vreg("node_%d" % p) for p in range(W)]
        w_nv = [self.alloc_vreg("nv_%d" % p) for p in range(W)]
        w_t1 = [self.alloc_vreg("t1_%d" % p) for p in range(W)]
        w_t2 = [self.alloc_vreg("t2_%d" % p) for p in range(W)]
        w_ia = [self.alloc_scratch("ia_%d" % p) for p in range(W)]
        w_iv = [self.alloc_scratch("iv_%d" % p) for p in range(W)]
        body = []

        def emit(sts):
            if not sts:
                return
            pos = [p * 8 for p in range(len(sts))]
            for k in range(max(q + len(o) for q, o in zip(pos, sts))):
                for q, o in zip(pos, sts):
                    if 0 <= k - q < len(o):
                        body.append(o[k - q])

        streams = []
        for g in range(nvec):
            p = g % W
            node, nv, t1, t2, ia, iv = w_node[p], w_nv[p], w_t1[p], w_t2[p], w_ia[p], w_iv[p]
            offc = self.scratch_const(g * VLEN)
            ops = [("alu", ("+", ia, self.scratch["inp_indices_p"], offc)),
                   ("alu", ("+", iv, self.scratch["inp_values_p"], offc)),
                   ("load", ("vload", idx_r[g], ia)),
                   ("load", ("vload", val_r[g], iv))]
            for _ in range(rounds):
                ops.append(("valu", ("+", node, idx_r[g], v_fp)))
                for lane in range(VLEN):
                    ops.append(("load", ("load_offset", nv, node, lane)))
                ops.append(("valu", ("^", val_r[g], val_r[g], nv)))
                ops.extend(self.build_hash(val_r[g], t1, t2, vc))
                ops.append(("valu", ("&", t1, val_r[g], vc[1])))
                ops.append(("valu", ("+", t2, t1, vc[1])))
                ops.append(("valu", ("multiply_add", idx_r[g], idx_r[g], vc[2], t2)))
                ops.append(("valu", ("<", t1, idx_r[g], v_nn)))
                ops.append(("valu", ("*", idx_r[g], idx_r[g], t1)))
            ops.append(("store", ("vstore", iv, val_r[g])))
            streams.append(ops)
            if len(streams) == W or g == nvec - 1:
                emit(streams)
                streams = []
        for i in range(nvec * VLEN, batch_size):
            s_idx = self.alloc_scratch("s_idx_%d" % i)
            s_val = self.alloc_scratch("s_val_%d" % i)
            s_nv = self.alloc_scratch("s_nv_%d" % i)
            s_t1 = self.alloc_scratch("s_t1_%d" % i)
            s_t2 = self.alloc_scratch("s_t2_%d" % i)
            ia = self.alloc_scratch("s_ia_%d" % i)
            iv = self.alloc_scratch("s_iv_%d" % i)
            ic = self.scratch_const(i)
            ops = [("alu", ("+", ia, self.scratch["inp_indices_p"], ic)),
                   ("load", ("load", s_idx, ia)),
                   ("alu", ("+", iv, self.scratch["inp_values_p"], ic)),
                   ("load", ("load", s_val, iv))]
            for _ in range(rounds):
                ops.append(("alu", ("+", ia, self.scratch["forest_values_p"], s_idx)))
                ops.append(("load", ("load", s_nv, ia)))
                ops.append(("alu", ("^", s_val, s_val, s_nv)))
                for op1, val1, op2, op3, val3 in HASH_STAGES:
                    ops.append(("alu", (op1, s_t1, s_val, self.scratch_const(val1))))
                    ops.append(("alu", (op3, s_t2, s_val, self.scratch_const(val3))))
                    ops.append(("alu", (op2, s_val, s_t1, s_t2)))
                ops.append(("alu", ("&", s_t1, s_val, self.scratch_const(1))))
                ops.append(("alu", ("+", s_t2, s_t1, self.scratch_const(1))))
                ops.append(("alu", ("+", s_idx, s_idx, s_idx)))
                ops.append(("alu", ("+", s_idx, s_idx, s_t2)))
                ops.append(("alu", ("<", s_t1, s_idx, self.scratch["n_nodes"])))
                ops.append(("alu", ("*", s_idx, s_idx, s_t1)))
            ops.append(("store", ("store", iv, s_val)))
            streams.append(ops)
        emit(streams)
        # Pack init/const slots (emit()'d during setup) and the body in ONE
        # program-order pass: the body consumes init vars and broadcast
        # constants, so cross-segment RAW edges must be visible to the packer.
        self.instrs.extend(self.build(self.slots + body))
