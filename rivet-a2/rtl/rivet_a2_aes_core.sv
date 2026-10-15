module rivet_a2_aes_core (
    input  logic         clk,
    input  logic         rst_n,
    input  logic         key_valid,
    output logic         key_ready,
    input  logic [255:0] key_in,
    input  logic         key_len_sel,
    output logic         key_loaded,
    input  logic         in_valid,
    output logic         in_ready,
    input  logic         in_enc_dec,
    input  logic [127:0] in_block,
    input  logic [7:0]   in_tag_id,
    output logic         out_valid,
    input  logic         out_ready,
    output logic [127:0] out_block,
    output logic [7:0]   out_tag_id,
    output logic         out_enc_dec,
    output logic         busy
);
    wire expanding, loaded, active;
    wire [3:0] round_index, rounds;
    wire [127:0] round_key;
    wire load, start;

    assign busy = rst_n && (expanding || active || out_valid);
    assign key_ready = rst_n && !busy;
    assign key_loaded = rst_n && loaded;
    assign in_ready = rst_n && loaded && !busy && !key_valid;
    assign load = key_valid && key_ready;
    assign start = in_valid && in_ready;

    rivet_a2_key_schedule u_key_schedule (
        .clk(clk), .rst_n(rst_n), .load(load), .key_in(key_in),
        .key_len_sel(key_len_sel), .round_index(round_index),
        .round_key(round_key), .rounds(rounds),
        .expanding(expanding), .loaded(loaded)
    );
    rivet_a2_datapath u_datapath (
        .clk(clk), .rst_n(rst_n), .start(start), .enc_dec(in_enc_dec),
        .block_in(in_block), .tag_in(in_tag_id), .rounds(rounds),
        .round_key(round_key), .out_ready(out_ready),
        .round_index(round_index), .active(active), .out_valid(out_valid),
        .out_block(out_block), .out_tag_id(out_tag_id),
        .out_enc_dec(out_enc_dec)
    );
endmodule
