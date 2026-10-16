// Adapted from supplied rivet_a2_reference/rtl/rivet_a2_key_schedule.sv.
module rivet_a3_key_schedule (
    input  logic         clk,
    input  logic         rst_n,
    input  logic         load,
    input  logic [255:0] key_in,
    input  logic         key_len_sel,
    input  logic [3:0]   round_index,
    output logic [127:0] round_key,
    output logic [3:0]   rounds,
    output logic         expanding,
    output logic         loaded
);
    import rivet_a3_pkg::*;
    logic [31:0] words [0:59];
    logic [5:0] word_index;
    logic key256;
    logic [7:0] rcon;
    logic [31:0] transformed, new_word;
    integer i;

    always @* begin
        transformed = 32'd0;
        new_word = 32'd0;
        if (expanding) begin
            transformed = words[word_index - 1];
            if ((!key256 && word_index[1:0] == 2'd0) ||
                (key256 && word_index[2:0] == 3'd0))
                transformed = sub_word({transformed[23:0], transformed[31:24]})
                              ^ {rcon, 24'd0};
            else if (key256 && word_index[2:0] == 3'd4)
                transformed = sub_word(transformed);
            if (key256)
                new_word = words[word_index - 8] ^ transformed;
            else
                new_word = words[word_index - 4] ^ transformed;
        end
    end

    assign round_key = (rst_n && loaded && round_index <= rounds)
        ? {words[{round_index, 2'b00}],
           words[{round_index, 2'b00} + 1],
           words[{round_index, 2'b00} + 2],
           words[{round_index, 2'b00} + 3]} : 128'd0;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (i = 0; i < 60; i = i + 1)
                words[i] <= 32'd0;
            rounds <= 4'd0;
            word_index <= 6'd0;
            key256 <= 1'b0;
            rcon <= 8'd0;
            expanding <= 1'b0;
            loaded <= 1'b0;
        end else if (load && !expanding) begin
            for (i = 0; i < 60; i = i + 1)
                words[i] <= 32'd0;
            for (i = 0; i < 4; i = i + 1)
                words[i] <= key_in[255-32*i -: 32];
            if (key_len_sel)
                for (i = 4; i < 8; i = i + 1)
                    words[i] <= key_in[255-32*i -: 32];
            if (key_len_sel) begin
                word_index <= 6'd8;
                rounds <= 4'd14;
            end else begin
                word_index <= 6'd4;
                rounds <= 4'd10;
            end
            key256 <= key_len_sel;
            rcon <= 8'h01;
            expanding <= 1'b1;
            loaded <= 1'b0;
        end else if (expanding) begin
            words[word_index] <= new_word;
            if ((!key256 && word_index[1:0] == 2'd0) ||
                (key256 && word_index[2:0] == 3'd0))
                rcon <= xtime(rcon);
            if ((!key256 && word_index == 6'd43) ||
                (key256 && word_index == 6'd59)) begin
                expanding <= 1'b0;
                loaded <= 1'b1;
                word_index <= 6'd0;
                rcon <= 8'd0;
            end else
                word_index <= word_index + 6'd1;
        end
    end
endmodule
