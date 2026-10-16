// Adapted from supplied rivet_a2_reference/rtl/rivet_a2_mixcolumns.sv.
module rivet_a3_mixcolumns (
    input  logic [127:0] state_in,
    input  logic         enc_dec,
    output logic [127:0] state_out
);
    import rivet_a3_pkg::*;
    genvar column, row;
    generate
        for (column = 0; column < 4; column = column + 1) begin : g_column
            for (row = 0; row < 4; row = row + 1) begin : g_row
                wire [7:0] a, b, c, d;
                assign a = state_in[127-8*(4*column+row) -: 8];
                assign b = state_in[127-8*(4*column+(row+1)%4) -: 8];
                assign c = state_in[127-8*(4*column+(row+2)%4) -: 8];
                assign d = state_in[127-8*(4*column+(row+3)%4) -: 8];
                assign state_out[127-8*(4*column+row) -: 8] = enc_dec
                    ? gf_mul(a, 8'h0e) ^ gf_mul(b, 8'h0b)
                      ^ gf_mul(c, 8'h0d) ^ gf_mul(d, 8'h09)
                    : gf_mul(a, 8'h02) ^ gf_mul(b, 8'h03) ^ c ^ d;
            end
        end
    endgenerate
endmodule
