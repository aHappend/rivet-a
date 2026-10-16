module rivet_a3_key_table (
    input wire clk, rst_n,
    input wire load_valid,
    output wire load_ready,
    input wire [1:0] slot_id,
    input wire [255:0] key_in,
    input wire key_len_sel, lock_in,
    input wire [3:0] bound_mask,
    output wire result_valid,
    input wire result_ready,
    output wire [3:0] result_code,
    input wire [1:0] read_slot_id,
    output wire [255:0] read_key,
    output wire read_key_len,
    output wire [3:0] valid_mask, lock_mask
);
    reg awake, pending;
    reg [3:0] code, valid_bits, locks, lengths;
    reg [255:0] keys [0:3];
    integer i;
    assign load_ready = rst_n && awake && !pending;
    assign result_valid = rst_n && awake && pending;
    assign result_code = result_valid ? code : 4'd0;
    assign valid_mask = rst_n && awake ? valid_bits : 4'd0;
    assign lock_mask = rst_n && awake ? locks : 4'd0;
    assign read_key = rst_n && awake && valid_bits[read_slot_id] ?
                      keys[read_slot_id] : 256'd0;
    assign read_key_len = rst_n && awake && valid_bits[read_slot_id] &&
                         lengths[read_slot_id];
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            awake <= 0;
            pending <= 0;
            code <= 0;
            valid_bits <= 0;
            locks <= 0;
            lengths <= 0;
            for (i=0; i<4; i=i+1) keys[i] <= 0;
        end else begin
            awake <= 1;
            if (pending && result_ready) begin
                pending <= 0;
                code <= 0;
            end
            if (load_valid && load_ready) begin
                pending <= 1;
                if (locks[slot_id] || bound_mask[slot_id])
                    code <= 3;
                else begin
                    keys[slot_id] <= key_len_sel ? key_in : {key_in[255:128],128'd0};
                    lengths[slot_id] <= key_len_sel;
                    locks[slot_id] <= lock_in;
                    valid_bits[slot_id] <= 1;
                    code <= 0;
                end
            end
        end
    end
endmodule
