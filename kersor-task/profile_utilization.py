import os
import sys
print("Starting profile script...")

# Add parent directory to path so we can import vliw modules
currentdir = os.path.dirname(os.path.abspath(__file__))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

from perf_takehome import KernelBuilder

def profile():
    # Standard test parameters used in submission_tests.py
    forest_height = 10
    n_nodes = 2047 # For height 10, typically 2^(h+1)-1
    batch_size = 256
    rounds = 16
    
    print(f"Profiling KernelBuilder with {forest_height=}, {n_nodes=}, {batch_size=}, {rounds=}")
    kb = KernelBuilder()
    try:
        kb.build_kernel(forest_height, n_nodes, batch_size, rounds)
    except Exception as e:
        print(f"Error building kernel: {e}")
        return

    instrs = kb.instrs
    total_cycles = len(instrs)
    
    print(f"Total Cycles (Bundles): {total_cycles}")
    
    # Slot limits from problem.py
    LIMITS = {
        'alu': 12,
        'valu': 6,
        'load': 2,
        'store': 2,
        'flow': 1
    }
    
    # Divide execution into segments to find bottlenecks (windup, middle, drain)
    segment_size = max(1, total_cycles // 10)
    segments = []
    for i in range(0, total_cycles, segment_size):
        segments.append(instrs[i:i+segment_size])
        
    print("\n--- Slot Utilization by Segment ---")
    for idx, seg in enumerate(segments):
        start = idx * segment_size
        end = min(start + segment_size, total_cycles)
        
        usage = {k: 0 for k in LIMITS.keys()}
        capacity = {k: LIMITS[k] * len(seg) for k in LIMITS.keys()}
        
        for bundle in seg:
            for engine in LIMITS.keys():
                usage[engine] += len(bundle.get(engine, []))
                
        stats = []
        for engine in LIMITS.keys():
            if capacity[engine] > 0:
                util = usage[engine] / capacity[engine] * 100
                stats.append(f"{engine} {util:5.1f}% ({usage[engine]}/{capacity[engine]})")
                
        print(f"Cycles [{start:4d}-{end:4d}]: " + " | ".join(stats))

if __name__ == '__main__':
    profile()
