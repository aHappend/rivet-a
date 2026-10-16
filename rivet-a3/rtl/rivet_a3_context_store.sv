module rivet_a3_context_store (
    input wire clk, rst_n,
    input wire write_en,
    input wire [1:0] write_id,
    input wire [1279:0] write_data,
    input wire [1:0] read_id,
    output wire [1279:0] read_data,
    input wire clear_en,
    input wire [1:0] clear_id
);
    reg [1279:0] records [0:3];
    integer i;
    assign read_data = rst_n ? records[read_id] : 1280'd0;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (i=0; i<4; i=i+1) records[i] <= 0;
        end else if (clear_en)
            records[clear_id] <= 0;
        else if (write_en)
            records[write_id] <= write_data;
    end
endmodule
