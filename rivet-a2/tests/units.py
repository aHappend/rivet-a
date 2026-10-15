"""Pin-level unit contracts: all round keys, service latency and GHASH arithmetic."""

import random
from reference import expand, gf128
from scenarios import svhex


def bench():
    lines = [r"""
`timescale 1ns/1ps
module tb_units;
reg clk=0;
always #5 clk=!clk;
reg rst_n;
reg load=0, key_len_sel=0;
reg [255:0] key_in=0;
reg [3:0] round_index=0;
wire [127:0] round_key;
wire [3:0] rounds;
wire expanding, loaded;
rivet_a2_key_schedule schedule(
.clk(clk),.rst_n(rst_n),.load(load),.key_in(key_in),.key_len_sel(key_len_sel),
.round_index(round_index),.round_key(round_key),.rounds(rounds),
.expanding(expanding),.loaded(loaded));
reg clear=0,start=0;
reg [127:0] x=0,h=0;
wire busy,done;
wire [127:0] result;
rivet_a2_ghash hash(
.clk(clk),.rst_n(rst_n),.clear(clear),.start(start),.x(x),.h(h),
.busy(busy),.done(done),.result(result));
integer i, key_comparisons=0, hash_comparisons=0;
task automatic tick;
begin @(posedge clk); #2; @(negedge clk); #1; end
endtask
task automatic check_reset;
begin
if ({round_key,rounds,expanding,loaded,busy,done,result} !== 0)
$fatal(1,"UNIT_RESET");
end
endtask
always @(posedge clk) begin
if(!rst_n) check_reset();
else if ((^{round_key,rounds,expanding,loaded,busy,done,result}) === 1'bx)
$fatal(1,"UNIT_XZ");
end
always @(negedge clk) if(!rst_n) check_reset();
initial begin
rst_n=0; #1; check_reset(); tick(); tick(); rst_n=1; tick();
"""]
    rng = random.Random(42019)
    for size in (16, 32, 16):
        key = rng.randbytes(size)
        packed = key + (rng.randbytes(16) if size == 16 else b"")
        duration = 40 if size == 16 else 52
        lines.append(f"key_in={svhex(packed)}; key_len_sel={int(size == 32)}; load=1; tick(); load=0;")
        lines.append(f'if(!expanding || loaded || rounds !== {10 if size == 16 else 14}) $fatal(1,"UNIT_KEY_LOAD");')
        lines.append(f"key_in=~key_in; key_len_sel=~key_len_sel; for(i=1;i<={duration};i=i+1) begin tick();")
        lines.append(f'if(loaded !== (i=={duration}) || expanding !== (i!={duration})) $fatal(1,"UNIT_KEY_LATENCY"); end')
        for index, rk in enumerate(expand(key)):
            lines.append(f"round_index={index}; #1;")
            lines.append(f'if(round_key !== {svhex(rk)}) $fatal(1,"UNIT_ROUND_KEY index={index}"); key_comparisons=key_comparisons+1;')
        lines.append("round_index=15; #1;")
        lines.append('if(round_key !== 0) $fatal(1,"UNIT_KEY_BOUND"); tick();')
    for a, b in [(0, 0), (1 << 127, 1 << 127), ((1 << 128) - 1, 1),
                 (1, (1 << 128) - 1)] + [(rng.getrandbits(128), rng.getrandbits(128)) for _ in range(12)]:
        expected = gf128(a, b)
        lines.append(f"x=128'h{a:032x}; h=128'h{b:032x}; start=1; tick(); start=0;")
        lines.append('if(!busy || done || result !== 0) $fatal(1,"UNIT_HASH_ACCEPT");')
        lines.append("x=~x; h=~h;")
        # Busy starts must not overwrite the accepted operands.
        lines.append("for(i=1;i<=128;i=i+1) begin start=(i==23); tick();")
        lines.append('if(done !== (i==128) || busy !== (i!=128)) $fatal(1,"UNIT_HASH_LATENCY"); end start=0;')
        lines.append(f'if(result !== 128\'h{expected:032x}) $fatal(1,"UNIT_HASH_RESULT");')
        lines.append('tick(); if(done || busy) $fatal(1,"UNIT_HASH_DONE_PULSE"); hash_comparisons=hash_comparisons+1;')
    lines.append(r"""
start=1; x=~128'd0; h=~128'd0; tick(); start=0; repeat(7) tick();
clear=1; start=1; tick(); clear=0; start=0;
if(busy || done || result !== 0) $fatal(1,"UNIT_HASH_CLEAR_PRIORITY");
repeat(130) tick();
if(busy || done || result !== 0) $fatal(1,"UNIT_HASH_ABORT");
#1; rst_n=0; #1; check_reset(); tick(); rst_n=1; tick();
if(key_comparisons != 37 || hash_comparisons != 16) $fatal(1,"UNIT_COVERAGE");
$display("UNIT_COUNTS round_keys=%0d hashes=%0d",key_comparisons,hash_comparisons);
$display("SIMULATION_COMPLETE");
$finish;
end
endmodule
""")
    return "\n".join(lines)
