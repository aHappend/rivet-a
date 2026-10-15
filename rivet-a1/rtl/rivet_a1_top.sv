module rivet_a1_top (
    input  logic         clk,
    input  logic         rst_n,
    input  logic         key_valid,
    output logic        key_ready,
    input  logic [127:0] key_in,
    output logic        key_loaded,
    input  logic         in_valid,
    output logic        in_ready,
    input  logic         in_enc_dec,
    input  logic [127:0] in_block,
    input  logic [7:0]   in_tag_id,
    output logic        out_valid,
    input  logic         out_ready,
    output logic [127:0] out_block,
    output logic [7:0]   out_tag_id,
    output logic        out_enc_dec,
    output logic        busy,
    output logic        err_unloaded_key
);
    wire expanding, loaded, active;
    wire [3:0] round_index;
    wire [127:0] round_key;
    wire load, start;

    assign busy = rst_n && (expanding || active || out_valid);
    assign key_ready = rst_n && !busy;
    assign key_loaded = rst_n && loaded;
    assign in_ready = rst_n && key_loaded && !busy && !key_valid;
    assign err_unloaded_key = 1'b0;
    assign load = key_valid && key_ready;
    assign start = in_valid && in_ready;

    rivet_a1_key_schedule u_key_schedule (
        .clk(clk), .rst_n(rst_n), .load(load), .key_in(key_in),
        .round_index(round_index), .round_key(round_key),
        .expanding(expanding), .loaded(loaded)
    );
    rivet_a1_datapath u_datapath (
        .clk(clk), .rst_n(rst_n), .start(start), .enc_dec(in_enc_dec),
        .block_in(in_block), .tag_in(in_tag_id), .round_key(round_key),
        .out_ready(out_ready), .round_index(round_index), .active(active),
        .out_valid(out_valid), .out_block(out_block), .out_tag_id(out_tag_id),
        .out_enc_dec(out_enc_dec)
    );
endmodule
