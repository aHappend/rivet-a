module rivet_a2_ghash (
    input  logic         clk,
    input  logic         rst_n,
    input  logic         clear,
    input  logic         start,
    input  logic [127:0] x,
    input  logic [127:0] h,
    output logic         busy,
    output logic         done,
    output logic [127:0] result
);
    logic [127:0] operand, v, z;
    logic [6:0] bit_index;
    wire [127:0] z_next = z ^ (operand[127] ? v : 128'd0);
    wire [127:0] v_next = (v >> 1) ^
        (v[0] ? 128'he1000000000000000000000000000000 : 128'd0);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            operand <= 128'd0;
            v <= 128'd0;
            z <= 128'd0;
            bit_index <= 7'd0;
            busy <= 1'b0;
            done <= 1'b0;
            result <= 128'd0;
        end else if (clear) begin
            operand <= 128'd0;
            v <= 128'd0;
            z <= 128'd0;
            bit_index <= 7'd0;
            busy <= 1'b0;
            done <= 1'b0;
            result <= 128'd0;
        end else begin
            done <= 1'b0;
            if (busy) begin
                if (bit_index == 7'd127) begin
                    result <= z_next;
                    busy <= 1'b0;
                    done <= 1'b1;
                    operand <= 128'd0;
                    v <= 128'd0;
                    z <= 128'd0;
                    bit_index <= 7'd0;
                end else begin
                    operand <= operand << 1;
                    v <= v_next;
                    z <= z_next;
                    bit_index <= bit_index + 7'd1;
                end
            end else if (start) begin
                operand <= x;
                v <= h;
                z <= 128'd0;
                bit_index <= 7'd0;
                result <= 128'd0;
                busy <= 1'b1;
            end
        end
    end
endmodule
