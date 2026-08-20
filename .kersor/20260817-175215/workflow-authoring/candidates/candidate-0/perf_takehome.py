class KernelBuilder:
    def __init__(self):
        self.instrs = []
        self.scratch = {}
        self.scratch_debug = {}
        self.scratch_ptr = 0
        self.const_map = {}

    def debug_info(self):
        return DebugInfo(scratch_map=self.scratch_debug)

    def build(self, slots: list[tuple[Engine, tuple]], vliw: bool = False):
        """Pack dependency-independent operations into legal VLIW bundles.

        Each bundle represents one cycle.  The scheduler uses a conservative
        scratch-register scoreboard: a slot cannot share a bundle with another
        slot when it reads a value written by that slot, writes a value read by
        that slot, or writes the same location.  Independent batch lanes can
        therefore fill the available ALU, load, store, and flow capacity.
        """
        limits = {
            "alu": 12,
            "valu": 6,
            "load": 2,
            "store": 2,
            "flow": 1,
            "debug": 64,
        }

        def rw(engine, op):
            if engine == "debug":
                return set(), set()

            if engine == "alu":
                return {op[1]}, {op[2], op[3]}

            if engine == "valu":
                if op[0] == "vbroadcast":
                    return set(range(op[1], op[1] + VLEN)), {op[2]}
                if op[0] == "multiply_add":
                    reads = set(range(op[2], op[2] + VLEN))
                    reads |= set(range(op[3], op[3] + VLEN))
                    reads |= set(range(op[4], op[4] + VLEN))
                    return set(range(op[1], op[1] + VLEN)), reads
                writes = set(range(op[1], op[1] + VLEN))
                reads = set(range(op[2], op[2] + VLEN))
                reads |= set(range(op[3], op[3] + VLEN))
                return writes, reads

            if engine == "load":
                if op[0] == "const":
                    return {op[1]}, set()
                if op[0] == "load_offset":
                    return {op[1] + op[3]}, {op[2]}
                if op[0] == "vload":
                    return set(range(op[1], op[1] + VLEN)), {op[2]}
                return {op[1]}, {op[2]}

            if engine == "store":
                if op[0] == "vstore":
                    return set(), {op[1], *range(op[2], op[2] + VLEN)}
                return set(), {op[1], op[2]}

            if engine == "flow":
                if op[0] == "select":
                    return {op[1]}, {op[2], op[3], op[4]}
                if op[0] == "vselect":
                    writes = set(range(op[1], op[1] + VLEN))
                    reads = set(range(op[2], op[2] + VLEN))
                    reads |= set(range(op[3], op[3] + VLEN))
                    reads |= set(range(op[4], op[4] + VLEN))
                    return writes, reads
                if op[0] == "add_imm":
                    return {op[1]}, {op[2]}
                if op[0] in ("cond_jump", "cond_jump_rel"):
                    return set(), {op[1]}
                if op[0] == "jump_indirect":
                    return set(), {op[1]}
                if op[0] == "trace_write":
                    return set(), {op[1]}
                return set(), set()

            return set(), set()

        pending = list(slots)
        result = []

        while pending:
            # Debug comparisons must observe committed writes.  Treat the
            # first debug slot as a zero-cycle ordering barrier and never pack
            # operations from after it into the preceding bundle.
            if pending[0][0] == "debug":
                result.append({"debug": [pending.pop(0)[1]]})
                continue

            bundle = {}
            reads = set()
            writes = set()
            chosen = []

            for index, (engine, op) in enumerate(pending):
                if engine == "debug":
                    break
                if len(bundle.get(engine, [])) >= limits[engine]:
                    continue

                slot_writes, slot_reads = rw(engine, op)
                if slot_writes & (reads | writes):
                    continue
                if slot_reads & writes:
                    continue

                bundle.setdefault(engine, []).append(op)
                reads |= slot_reads
                writes |= slot_writes
                chosen.append(index)

            if not chosen:
                raise AssertionError("VLIW scheduler made no progress")

            for index in reversed(chosen):
                pending.pop(index)
            result.append(bundle)

        return result

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

    def build_hash(self, val_hash_addr, tmp1, tmp2, round, i):
        slots = []
        for hi, (op1, val1, op2, op3, val3) in enumerate(HASH_STAGES):
            slots.append(("alu", (op1, tmp1, val_hash_addr, self.scratch_const(val1))))
            slots.append(("alu", (op3, tmp2, val_hash_addr, self.scratch_const(val3))))
            slots.append(("alu", (op2, val_hash_addr, tmp1, tmp2)))
            slots.append(("debug", ("compare", val_hash_addr, (round, i, "hash_stage", hi))))
        return slots

    def build_kernel(self, forest_height: int, n_nodes: int, batch_size: int, rounds: int):
        tmp1 = self.alloc_scratch("tmp1")
        tmp2 = self.alloc_scratch("tmp2")
        tmp3 = self.alloc_scratch("tmp3")

        init_vars = [
            "rounds",
            "n_nodes",
            "batch_size",
            "forest_height",
            "forest_values_p",
            "inp_indices_p",
            "inp_values_p",
        ]
        for name in init_vars:
            self.alloc_scratch(name)

        for i, name in enumerate(init_vars):
            self.add("load", ("const", tmp1, i))
            self.add("load", ("load", self.scratch[name], tmp1))

        zero_const = self.scratch_const(0)
        one_const = self.scratch_const(1)
        two_const = self.scratch_const(2)

        self.add("flow", ("pause",))
        self.add("debug", ("comment", "Starting loop"))

        body = []

        # Six scalar scratch words per batch lane are sufficient:
        # idx, val, node/address, and two hash temporaries.  The node word is
        # reused as the branch increment after the gather is consumed.
        for round_index in range(rounds):
            for batch_index in range(batch_size):
                idx = self.alloc_scratch()
                val = self.alloc_scratch()
                node_or_addr = self.alloc_scratch()
                addr = self.alloc_scratch()
                hash_tmp1 = self.alloc_scratch()
                hash_tmp2 = self.alloc_scratch()

                body.append(("flow", ("add_imm", addr, self.scratch["inp_indices_p"], batch_index)))
                body.append(("load", ("load", idx, addr)))
                body.append(("debug", ("compare", idx, (round_index, batch_index, "idx"))))

                body.append(("flow", ("add_imm", addr, self.scratch["inp_values_p"], batch_index)))
                body.append(("load", ("load", val, addr)))
                body.append(("debug", ("compare", val, (round_index, batch_index, "val"))))

                body.append(("alu", ("+", addr, self.scratch["forest_values_p"], idx)))
                body.append(("load", ("load", node_or_addr, addr)))
                body.append(("debug", ("compare", node_or_addr, (round_index, batch_index, "node_val"))))

                body.append(("alu", ("^", val, val, node_or_addr)))

                for hash_stage, (op1, value1, op2, op3, value3) in enumerate(HASH_STAGES):
                    body.append(("alu", (op1, hash_tmp1, val, self.scratch_const(value1))))
                    body.append(("alu", (op3, hash_tmp2, val, self.scratch_const(value3))))
                    body.append(("alu", (op2, val, hash_tmp1, hash_tmp2)))
                    body.append(("debug", ("compare", val, (round_index, batch_index, "hash_stage", hash_stage))))

                body.append(("debug", ("compare", val, (round_index, batch_index, "hashed_val"))))

                body.append(("alu", ("%", hash_tmp1, val, two_const)))
                body.append(("alu", ("==", hash_tmp1, hash_tmp1, zero_const)))
                body.append(("flow", ("select", node_or_addr, hash_tmp1, one_const, two_const)))
                body.append(("alu", ("*", idx, idx, two_const)))
                body.append(("alu", ("+", idx, idx, node_or_addr)))
                body.append(("debug", ("compare", idx, (round_index, batch_index, "next_idx"))))

                body.append(("alu", ("<", hash_tmp1, idx, self.scratch["n_nodes"])))
                body.append(("flow", ("select", idx, hash_tmp1, idx, zero_const)))
                body.append(("debug", ("compare", idx, (round_index, batch_index, "wrapped_idx"))))

                body.append(("flow", ("add_imm", addr, self.scratch["inp_indices_p"], batch_index)))
                body.append(("store", ("store", addr, idx)))
                body.append(("flow", ("add_imm", addr, self.scratch["inp_values_p"], batch_index)))
                body.append(("store", ("store", addr, val)))

        self.instrs.extend(self.build(body, vliw=True))
        self.instrs.append({"flow": [("pause",)]})