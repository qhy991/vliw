# VLIW Kernel Optimization Task

You are an expert performance engineer optimizing a VLIW list scheduler for a custom Python simulator.

## Goal
Minimize the total execution cycles by modifying `KernelBuilder.build_kernel()` in `/Users/haiyan-mini/Agent4Kernel/vliw/perf_takehome.py`. 
Do NOT modify any files in the `tests/` directory as it will cause validation to fail.

## Architecture Constraints
Each cycle (bundle) can contain up to:
- 12 ALU slots
- 6 VALU (Vector ALU) slots
- 2 Load slots
- 2 Store slots
- 1 Flow slot

Vector operations (`self.v_alu`, `self.v_muladd`) operate on `VLEN=8` lanes and use 1 VALU slot.
Alternatively, `self.v_alu_scalar` breaks a vector op into 8 scalar ops, using 8 ALU slots.

## The Optimization Problem
The default code might be bottle-necked on ALU or VALU. The key optimization is to balance the operations across the available ALU and VALU slots in each bundle.
For instance, if VALU is fully utilized but ALU is empty, you can convert some `v_alu` calls to `v_alu_scalar` to offload work to the ALU. Or vice-versa. 
Also consider that the utilization might differ during windup, middle, and drain phases of the execution!

## Metrics
Cycles. Lower is better. The `eval.sh` wrapper script executes the tests and returns this metric as `Time: <cycles> ms`.
To understand the current bottleneck, run `python kersor-task/profile_utilization.py` to see the slot utilization across different phases of execution.
