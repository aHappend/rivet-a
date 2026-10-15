module rivet_a2_sbox (
    input  logic [127:0] state_in,
    input  logic         enc_dec,
    output logic [127:0] state_out
);
    import rivet_a2_pkg::*;
    genvar byte_index;
    generate
        for (byte_index = 0; byte_index < 16; byte_index = byte_index + 1) begin : g_byte
            assign state_out[127-8*byte_index -: 8] =
                aes_sub_byte(state_in[127-8*byte_index -: 8], enc_dec);
        end
    endgenerate
endmodule
