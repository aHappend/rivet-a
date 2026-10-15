module rivet_a1_key_schedule (
    input  logic         clk,
    input  logic         rst_n,
    input  logic         load,
    input  logic [127:0] key_in,
    input  logic [3:0]   round_index,
    output logic [127:0] round_key,
    output logic        expanding,
    output logic        loaded
);
    import rivet_a1_pkg::*;
    logic [127:0] round_keys [0:10];
    logic [127:0] previous_key;
    logic [3:0] expand_index;
    logic [7:0] rcon;
    wire [127:0] expanded_key;
    integer index;

    assign expanded_key = next_round_key(previous_key, rcon);
    assign round_key = (round_index <= 4'd10) ? round_keys[round_index] : 128'd0;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (index = 0; index < 11; index = index + 1)
                round_keys[index] <= 128'd0;
            previous_key <= 128'd0;
            expand_index <= 4'd0;
            rcon <= 8'd0;
            expanding <= 1'b0;
            loaded <= 1'b0;
        end else if (load && !expanding) begin
            round_keys[0] <= key_in;
            previous_key <= key_in;
            expand_index <= 4'd1;
            rcon <= 8'h01;
            expanding <= 1'b1;
            loaded <= 1'b0;
        end else if (expanding) begin
            round_keys[expand_index] <= expanded_key;
            previous_key <= expanded_key;
            rcon <= xtime(rcon);
            if (expand_index == 4'd10) begin
                expanding <= 1'b0;
                loaded <= 1'b1;
            end else begin
                expand_index <= expand_index + 4'd1;
            end
        end
    end
endmodule
