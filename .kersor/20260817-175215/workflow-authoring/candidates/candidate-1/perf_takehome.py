from problem import HASH_STAGES, SCRATCH_SIZE, VLEN


class KernelBuilder:
    def __init__(self):
        self.instrs = []
        self.scratch = {}
        self.scratch_debug = {}
        self.scratch_ptr = 0
        self.const_map = {}
        self._vector_const_map = {}

    def debug_info(self):
        from problem import DebugInfo
        return DebugInfo(scratch_map=self.scratch_debug)

    @staticmethod
    def _slot_accesses(engine, slot):
        """Return (read addresses, written addresses) for dependency-aware packing."""
        reads = set()
        writes = set()

        def add_range(base, length=1, target=None):
            collection = writes if target == "write" else reads
            collection.update(range(base, base + length))

        if engine == "alu":
            _, dest, a1, a2 = slot
            add_range(a1)
            add_range(a2)
            add_range(dest, target="write")
        elif engine == "valu":
            if slot[0] == "vbroadcast":
                _, dest, src = slot
                add_range(src)
                add_range(dest, VLEN, target="write")
            elif slot[0] == "multiply_add":
                _, dest, a, b, c = slot
                add_range(a, VLEN)
                add_range(b, VLEN)
                add_range(c, VLEN)
                add_range(dest, VLEN, target="write")
            else:
                _, dest, a1, a2 = slot
                add_range(a1, VLEN)
                add_range(a2, VLEN)
                add_range(dest, VLEN, target="write")
        elif engine == "load":
            op = slot[0]
            if op == "const":
                _, dest, _ = slot
                add_range(dest, target="write")
            elif op == "load":
                _, dest, addr = slot
                add_range(addr)
                add_range(dest, target="write")
            elif op == "load_offset":
                _, dest, addr, offset = slot
                add_range(addr + offset)
                add_range(dest + offset, target="write")
            elif op == "vload":
                _, dest, addr = slot
                add_range(addr)
                add_range(dest, VLEN, target="write")
        elif engine == "store":
            _, addr, src = slot
            add_range(addr)
            if slot[0] == "vstore":
                add_range(src, VLEN)
            else:
                add_range(src)
        elif engine == "flow":
            op = slot[0]
            if op == "select":
                _, dest, cond, a, b = slot
                add_range(cond)
                add_range(a)
                add_range(b)
                add_range(dest, target="write")
            elif op == "vselect":
                _, dest, cond, a, b = slot
                add_range(cond, VLEN)
                add_range(a, VLEN)
                add_range(b, VLEN)
                add_range(dest, VLEN, target="write")
            elif op == "add_imm":
                _, dest, src, _ = slot
                add_range(src)
                add_range(dest, target="write")
            elif op in ("cond_jump", "cond_jump_rel"):
                add_range(slot[1])
            elif op in ("trace_write", "jump_indirect", "coreid"):
                if op != "coreid":
                    add_range(slot[1])
                else:
                    add_range(slot[1], target="write")
            elif op not in ("pause", "halt", "jump"):
                for value in slot[1:]:
                    if isinstance(value, int):
                        add_range(value)
        elif engine == "debug":
            if slot[0] in ("compare", "vcompare"):
                add_range(slot[1], VLEN if slot[0] == "vcompare" else 1)

        return reads, writes

    def build(self, slots, vliw=False):
        """Pack a topologically ordered slot stream into legal VLIW bundles.

        The scheduler never reorders slots. It only places a slot in the current
        bundle when engine capacity and scratch read/write dependencies permit it.
        This preserves the simulator's end-of-cycle write semantics while allowing
        independent lanes and engines to issue together.
        """
        if not vliw:
            return [{engine: [slot]} for engine, slot in slots]

        bundles = []
        current = {}
        current_reads = set()
        current_writes = set()

        def flush():
            nonlocal current, current_reads, current_writes
            if current:
                bundles.append(current)
            current = {}
            current_reads = set()
            current_writes = set()

        for engine, slot in slots:
            if engine == "debug":
                flush()
                bundles.append({"debug": [slot]})
                continue

            reads, writes = self._slot_accesses(engine, slot)
            limit = {"alu": 12, "valu": 6, "load": 2, "store": 2, "flow": 1}.get(engine, 64)
            engine_full = len(current.get(engine, [])) >= limit
            hazard = bool(reads & current_writes) or bool(writes & current_reads) or bool(writes & current_writes)

            if engine_full or hazard:
                flush()

            current.setdefault(engine, []).append(slot)
            current_reads.update(reads)
            current_writes.update(writes)

        flush()
        return bundles

    def add(self, engine, slot):
        self.instrs.append({engine: [slot]})

    def alloc_scratch(self, name=None, length=1):
        addr = self.scratch_ptr
        if name is not None:
            self.scratch[name] = addr
            self.scratch_debug[addr] = (name, length)
        self.scratch_ptr += length
        assert self.scratch_ptr <= SCRATCH_SIZE, "Out of scratch space"
        return addr

    def scratch_const(self, val, name=None):
        if val not in self.const_map:
            addr = self.alloc_scratch(name)
            self.add("load", ("const", addr, val))
            self.const_map[val] = addr
        return self.const_map[val]

    def vector_const(self, val):
        if val not in self._vector_const_map:
            scalar = self.scratch_const(val)
            addr = self.alloc_scratch(length=VLEN)
            self.add("valu", ("vbroadcast", addr, scalar))
            self._vector_const_map[val] = addr
        return self._vector_const_map[val]

    def build_hash(self, val_hash_addr, tmp1, tmp2, round, i):
        slots = []
        for hi, (op1, val1, op2, op3, val3) in enumerate(HASH_STAGES):
            slots.append(("alu", (op1, tmp1, val_hash_addr, self.scratch_const(val1))))
            slots.append(("alu", (op3, tmp2, val_hash_addr, self.scratch_const(val3))))
            slots.append(("alu", (op2, val_hash_addr, tmp1, tmp2)))
            slots.append(("debug", ("compare", val_hash_addr, (round, i, "hash_stage", hi))))
        return slots

    def build_kernel(self, forest_height: int, n_nodes: int, batch_size: int, rounds: int):
        tmp = self.alloc_scratch("tmp")
        init_vars = [
            "rounds", "n_nodes", "batch_size", "forest_height",
            "forest_values_p", "inp_indices_p", "inp_values_p",
        ]
        for name in init_vars:
            self.alloc_scratch(name)

        init_slots = []
        for i, name in enumerate(init_vars):
            init_slots.append(("load", ("const", tmp, i)))
            init_slots.append(("load", ("load", self.scratch[name], tmp)))
        self.instrs.extend(self.build(init_slots, vliw=True))

        one = self.scratch_const(1)
        two = self.scratch_const(2)
        batch_const = self.scratch_const(batch_size)
        zero_vec = self.vector_const(0)
        one_vec = self.vector_const(1)
        two_vec = self.vector_const(2)
        hash_vec_consts = {
            value: self.vector_const(value)
            for stage in HASH_STAGES
            for value in (stage[1], stage[4])
        }

        self.instrs.append({"flow": [("pause",)]})
        self.instrs.append({"debug": [("comment", "Starting loop")]})

        groups = []
        for start in range(0, batch_size, VLEN):
            idx = self.alloc_scratch(length=VLEN)
            val = self.alloc_scratch(length=VLEN)
            gather = self.alloc_scratch(length=VLEN)
            htmp = self.alloc_scratch(length=VLEN)
            idx_addr = self.alloc_scratch()
            val_addr = self.alloc_scratch()
            groups.append((start, idx, val, gather, htmp, idx_addr, val_addr))

        for round_index in range(rounds):
            body = []
            for start, idx, val, gather, htmp, idx_addr, val_addr in groups:
                body.append(("flow", ("add_imm", idx_addr, self.scratch["inp_indices_p"], start)))
            for start, idx, val, gather, htmp, idx_addr, val_addr in groups:
                body.append(("alu", ("+", val_addr, idx_addr, batch_const)))
            for start, idx, val, gather, htmp, idx_addr, val_addr in groups:
                body.append(("load", ("vload", idx, idx_addr)))
                body.append(("load", ("vload", val, val_addr)))
            for start, idx, val, gather, htmp, idx_addr, val_addr in groups:
                for lane in range(VLEN):
                    body.append(("alu", ("+", gather + lane, self.scratch["forest_values_p"], idx + lane)))
            for start, idx, val, gather, htmp, idx_addr, val_addr in groups:
                for lane in range(VLEN):
                    body.append(("load", ("load", gather + lane, gather + lane)))
            for start, idx, val, gather, htmp, idx_addr, val_addr in groups:
                body.append(("valu", ("^", val, val, gather)))
            for op1, value1, op2, op3, value3 in HASH_STAGES:
                for start, idx, val, gather, htmp, idx_addr, val_addr in groups:
                    body.append(("valu", (op1, htmp, val, hash_vec_consts[value1])))
                    body.append(("valu", (op3, gather, val, hash_vec_consts[value3])))
                for start, idx, val, gather, htmp, idx_addr, val_addr in groups:
                    body.append(("valu", (op2, val, htmp, gather)))
            for start, idx, val, gather, htmp, idx_addr, val_addr in groups:
                body.append(("valu", ("%", htmp, val, two_vec)))
            for start, idx, val, gather, htmp, idx_addr, val_addr in groups:
                body.append(("valu", ("==", htmp, htmp, zero_vec)))
            for start, idx, val, gather, htmp, idx_addr, val_addr in groups:
                body.append(("flow", ("vselect", gather, htmp, one_vec, two_vec)))
                body.append(("valu", ("*", idx, idx, two_vec)))
            for start, idx, val, gather, htmp, idx_addr, val_addr in groups:
                body.append(("valu", ("+", idx, idx, gather)))
            n_nodes_vec = self.vector_const(n_nodes)
            for start, idx, val, gather, htmp, idx_addr, val_addr in groups:
                body.append(("valu", ("<", htmp, idx, n_nodes_vec)))
            for start, idx, val, gather, htmp, idx_addr, val_addr in groups:
                body.append(("flow", ("vselect", idx, htmp, idx, zero_vec)))
            for start, idx, val, gather, htmp, idx_addr, val_addr in groups:
                body.append(("store", ("vstore", idx_addr, idx)))
                body.append(("store", ("vstore", val_addr, val)))

            self.instrs.extend(self.build(body, vliw=True))
            self.instrs.append({"flow": [("pause",)]})