module rivet_a2_datapath (
    input  logic         clk,
    input  logic         rst_n,
    input  logic         start,
    input  logic         enc_dec,
    input  logic [127:0] block_in,
    input  logic [7:0]   tag_in,
    input  logic [3:0]   rounds,
    input  logic [127:0] round_key,
    input  logic         out_ready,
    output logic [3:0]   round_index,
    output logic         active,
    output logic         out_valid,
    output logic [127:0] out_block,
    output logic [7:0]   out_tag_id,
    output logic         out_enc_dec
);
    logic [127:0] state;
    logic mode;
    logic [7:0] tag;
    logic [3:0] round_number;
    wire [127:0] substituted, shifted, mix_input, mixed, round_result;

    assign round_index = active
        ? (mode ? rounds - round_number : round_number)
        : (enc_dec ? rounds : 4'd0);

    rivet_a2_sbox u_sbox (
        .state_in(state), .enc_dec(mode), .state_out(substituted)
    );
    rivet_a2_shiftrows u_shiftrows (
        .state_in(substituted), .enc_dec(mode), .state_out(shifted)
    );
    // Inverse SubBytes and inverse ShiftRows commute; keys precede inverse mixing.
    assign mix_input = mode ? shifted ^ round_key : shifted;
    rivet_a2_mixcolumns u_mixcolumns (
        .state_in(mix_input), .enc_dec(mode), .state_out(mixed)
    );
    assign round_result = (round_number == rounds)
        ? shifted ^ round_key
        : (mode ? mixed : mixed ^ round_key);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= 128'd0;
            mode <= 1'b0;
            tag <= 8'd0;
            round_number <= 4'd0;
            active <= 1'b0;
            out_valid <= 1'b0;
            out_block <= 128'd0;
            out_tag_id <= 8'd0;
            out_enc_dec <= 1'b0;
        end else begin
            if (out_valid && out_ready) begin
                out_valid <= 1'b0;
                out_block <= 128'd0;
                out_tag_id <= 8'd0;
                out_enc_dec <= 1'b0;
            end
            if (active) begin
                if (round_number == rounds) begin
                    state <= 128'd0;
                    mode <= 1'b0;
                    tag <= 8'd0;
                    round_number <= 4'd0;
                    active <= 1'b0;
                    out_valid <= 1'b1;
                    out_block <= round_result;
                    out_tag_id <= tag;
                    out_enc_dec <= mode;
                end else begin
                    state <= round_result;
                    round_number <= round_number + 4'd1;
                end
            end else if (start && !out_valid) begin
                state <= block_in ^ round_key;
                mode <= enc_dec;
                tag <= tag_in;
                round_number <= 4'd1;
                active <= 1'b1;
            end
        end
    end
endmodule
