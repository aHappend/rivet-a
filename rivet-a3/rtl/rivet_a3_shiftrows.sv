// Adapted from supplied rivet_a2_reference/rtl/rivet_a2_shiftrows.sv.
module rivet_a3_shiftrows (
    input  logic [127:0] state_in,
    input  logic         enc_dec,
    output logic [127:0] state_out
);
    genvar row, column;
    generate
        for (column = 0; column < 4; column = column + 1) begin : g_column
            for (row = 0; row < 4; row = row + 1) begin : g_row
                assign state_out[127-8*(4*column+row) -: 8] = enc_dec
                    ? state_in[127-8*(4*((column+4-row)%4)+row) -: 8]
                    : state_in[127-8*(4*((column+row)%4)+row) -: 8];
            end
        end
    endgenerate
endmodule
