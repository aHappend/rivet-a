module rivet_a2_top #(
    parameter integer MAX_PAYLOAD_BLOCKS = 16
) (
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
    output logic         busy,
    output logic         err_unloaded_key,
    input  logic         cmd_valid,
    output logic         cmd_ready,
    input  logic         cmd_decrypt,
    input  logic [95:0]  iv_in,
    input  logic [31:0]  aad_bytes,
    input  logic [31:0]  payload_bytes,
    input  logic [127:0] expected_tag,
    input  logic         data_valid,
    output logic         data_ready,
    input  logic         data_is_aad,
    input  logic [127:0] data_in,
    input  logic [4:0]   valid_bytes,
    output logic [4:0]   out_valid_bytes,
    output logic         out_is_gcm,
    input  logic         tag_ready,
    output logic         tag_valid,
    output logic [127:0] tag_out,
    output logic         tag_match,
    output logic         auth_fail,
    output logic         protocol_error
);
    typedef enum logic [4:0] {
        S_IDLE, S_KEY, S_RAW, S_H_START, S_H_WAIT,
        S_MASK_START, S_MASK_WAIT, S_NEXT, S_DATA,
        S_AAD_START, S_AAD_WAIT, S_PAY_START, S_PAY_WAIT,
        S_C_START, S_C_WAIT, S_LEN_START, S_LEN_WAIT,
        S_FINISH, S_SCRUB, S_TAG, S_DRAIN
    } state_t;
    state_t state;
    logic awake;
    logic decrypt_mode;
    logic [127:0] h_value, j0, counter, tag_mask, hash_value;
    logic [127:0] expected_latched, payload_hold, hash_block, tag_record;
    logic [31:0] aad_remaining, payload_remaining;
    logic [63:0] aad_bits, payload_bits;
    logic [4:0] beat_bytes;
    logic [8:0] write_count, drain_index, scrub_index;
    logic [127:0] payload_store [0:MAX_PAYLOAD_BLOCKS-1];
    logic [4:0] byte_store [0:MAX_PAYLOAD_BLOCKS-1];
    logic match_status, fail_status, error_status;
    logic aes_in_valid, aes_in_mode, aes_out_ready;
    logic [127:0] aes_in_block;
    logic [7:0] aes_in_tag;
    wire aes_key_ready, aes_loaded, aes_in_ready, aes_out_valid, aes_busy;
    wire [127:0] aes_out_block;
    wire [7:0] aes_out_tag;
    wire aes_out_mode;
    logic gh_start;
    logic [127:0] gh_x;
    wire gh_busy, gh_done;
    wire [127:0] gh_result;
    wire gh_clear = (state == S_IDLE || state == S_KEY || state == S_RAW ||
                     state == S_FINISH || state == S_SCRUB || state == S_TAG);
    wire key_transfer = key_valid && key_ready;
    wire cmd_transfer = cmd_valid && cmd_ready;
    wire raw_transfer = in_valid && in_ready;
    wire [31:0] section_remaining =
        (aad_remaining != 32'd0) ? aad_remaining : payload_remaining;
    wire [4:0] required_bytes =
        (section_remaining >= 32'd16) ? 5'd16 : section_remaining[4:0];
    wire [127:0] computed_tag = tag_mask ^ hash_value;
    wire [127:0] payload_result =
        mask_bytes(payload_hold ^ aes_out_block, beat_bytes);
    integer i;

    function automatic logic [127:0] mask_bytes(
        input logic [127:0] block_value,
        input logic [4:0] count
    );
        integer b;
        begin
            mask_bytes = 128'd0;
            for (b = 0; b < 16; b = b + 1)
                if (b < count)
                    mask_bytes[127-8*b -: 8] = block_value[127-8*b -: 8];
        end
    endfunction

    rivet_a2_aes_core u_aes_core (
        .clk(clk), .rst_n(rst_n), .key_valid(key_transfer),
        .key_ready(aes_key_ready), .key_in(key_in),
        .key_len_sel(key_len_sel), .key_loaded(aes_loaded),
        .in_valid(aes_in_valid), .in_ready(aes_in_ready),
        .in_enc_dec(aes_in_mode), .in_block(aes_in_block),
        .in_tag_id(aes_in_tag), .out_valid(aes_out_valid),
        .out_ready(aes_out_ready), .out_block(aes_out_block),
        .out_tag_id(aes_out_tag), .out_enc_dec(aes_out_mode),
        .busy(aes_busy)
    );
    rivet_a2_ghash u_ghash (
        .clk(clk), .rst_n(rst_n), .clear(gh_clear), .start(gh_start),
        .x(gh_x), .h(h_value), .busy(gh_busy), .done(gh_done),
        .result(gh_result)
    );

    always @* begin
        key_ready = 1'b0;
        key_loaded = 1'b0;
        in_ready = 1'b0;
        cmd_ready = 1'b0;
        data_ready = 1'b0;
        busy = 1'b0;
        err_unloaded_key = 1'b0;
        out_valid = 1'b0;
        out_block = 128'd0;
        out_tag_id = 8'd0;
        out_enc_dec = 1'b0;
        out_valid_bytes = 5'd0;
        out_is_gcm = 1'b0;
        tag_valid = 1'b0;
        tag_out = 128'd0;
        tag_match = 1'b0;
        auth_fail = 1'b0;
        protocol_error = 1'b0;
        if (rst_n && awake) begin
            key_loaded = aes_loaded;
            busy = (state != S_IDLE);
            tag_match = match_status;
            auth_fail = fail_status;
            protocol_error = error_status;
            if (state == S_IDLE) begin
                key_ready = aes_key_ready;
                cmd_ready = aes_loaded && !key_valid;
                in_ready = aes_in_ready && !key_valid && !cmd_valid;
            end
            data_ready = (state == S_DATA);
            if (state == S_RAW && aes_out_valid) begin
                out_valid = 1'b1;
                out_block = aes_out_block;
                out_tag_id = aes_out_tag;
                out_enc_dec = aes_out_mode;
                out_valid_bytes = 5'd16;
            end else if (state == S_DRAIN && drain_index < write_count) begin
                out_valid = 1'b1;
                out_block = payload_store[drain_index];
                out_enc_dec = decrypt_mode;
                out_valid_bytes = byte_store[drain_index];
                out_is_gcm = 1'b1;
            end
            if (state == S_TAG) begin
                tag_valid = 1'b1;
                tag_out = tag_record;
            end
        end
    end

    always @* begin
        aes_in_valid = 1'b0;
        aes_in_mode = 1'b0;
        aes_in_block = 128'd0;
        aes_in_tag = 8'd0;
        aes_out_ready = 1'b0;
        gh_start = 1'b0;
        gh_x = 128'd0;
        if (rst_n && awake) begin
            case (state)
                S_IDLE: begin
                    aes_in_valid = raw_transfer;
                    aes_in_mode = in_enc_dec;
                    aes_in_block = in_block;
                    aes_in_tag = in_tag_id;
                end
                S_RAW: aes_out_ready = out_ready;
                S_H_START: aes_in_valid = 1'b1;
                S_MASK_START: begin
                    aes_in_valid = 1'b1;
                    aes_in_block = j0;
                end
                S_PAY_START: begin
                    aes_in_valid = 1'b1;
                    aes_in_block = counter;
                end
                S_H_WAIT, S_MASK_WAIT, S_PAY_WAIT: aes_out_ready = 1'b1;
                S_AAD_START, S_C_START: begin
                    gh_start = 1'b1;
                    gh_x = hash_value ^ hash_block;
                end
                S_LEN_START: begin
                    gh_start = 1'b1;
                    gh_x = hash_value ^ {aad_bits, payload_bits};
                end
                default: begin end
            endcase
        end
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= S_IDLE;
            awake <= 1'b0;
            decrypt_mode <= 1'b0;
            h_value <= 128'd0;
            j0 <= 128'd0;
            counter <= 128'd0;
            tag_mask <= 128'd0;
            hash_value <= 128'd0;
            expected_latched <= 128'd0;
            payload_hold <= 128'd0;
            hash_block <= 128'd0;
            tag_record <= 128'd0;
            aad_remaining <= 32'd0;
            payload_remaining <= 32'd0;
            aad_bits <= 64'd0;
            payload_bits <= 64'd0;
            beat_bytes <= 5'd0;
            write_count <= 9'd0;
            drain_index <= 9'd0;
            scrub_index <= 9'd0;
            match_status <= 1'b0;
            fail_status <= 1'b0;
            error_status <= 1'b0;
            for (i = 0; i < MAX_PAYLOAD_BLOCKS; i = i + 1) begin
                payload_store[i] <= 128'd0;
                byte_store[i] <= 5'd0;
            end
        end else if (!awake) begin
            awake <= 1'b1;
        end else begin
            case (state)
                S_IDLE: begin
                    if (key_transfer) begin
                        match_status <= 1'b0;
                        fail_status <= 1'b0;
                        error_status <= 1'b0;
                        state <= S_KEY;
                    end else if (cmd_transfer) begin
                        match_status <= 1'b0;
                        fail_status <= 1'b0;
                        error_status <= 1'b0;
                        tag_record <= 128'd0;
                        decrypt_mode <= cmd_decrypt;
                        expected_latched <= expected_tag;
                        j0 <= {iv_in, 32'h00000001};
                        counter <= {iv_in, 32'h00000002};
                        aad_remaining <= aad_bytes;
                        payload_remaining <= payload_bytes;
                        aad_bits <= {32'd0, aad_bytes} << 3;
                        payload_bits <= {32'd0, payload_bytes} << 3;
                        h_value <= 128'd0;
                        hash_value <= 128'd0;
                        tag_mask <= 128'd0;
                        payload_hold <= 128'd0;
                        hash_block <= 128'd0;
                        beat_bytes <= 5'd0;
                        write_count <= 9'd0;
                        drain_index <= 9'd0;
                        scrub_index <= 9'd0;
                        if (payload_bytes > 16 * MAX_PAYLOAD_BLOCKS) begin
                            error_status <= 1'b1;
                            state <= S_SCRUB;
                        end else
                            state <= S_H_START;
                    end else if (raw_transfer) begin
                        match_status <= 1'b0;
                        fail_status <= 1'b0;
                        error_status <= 1'b0;
                        state <= S_RAW;
                    end
                end
                S_KEY: begin
                    if (aes_loaded && !aes_busy)
                        state <= S_IDLE;
                end
                S_RAW: begin
                    if (aes_out_valid && out_ready)
                        state <= S_IDLE;
                end
                S_H_START: begin
                    if (aes_in_ready)
                        state <= S_H_WAIT;
                end
                S_H_WAIT: begin
                    if (aes_out_valid) begin
                        h_value <= aes_out_block;
                        state <= S_MASK_START;
                    end
                end
                S_MASK_START: begin
                    if (aes_in_ready)
                        state <= S_MASK_WAIT;
                end
                S_MASK_WAIT: begin
                    if (aes_out_valid) begin
                        tag_mask <= aes_out_block;
                        j0 <= 128'd0;
                        state <= S_NEXT;
                    end
                end
                S_NEXT: begin
                    if (aad_remaining != 32'd0 || payload_remaining != 32'd0)
                        state <= S_DATA;
                    else
                        state <= S_LEN_START;
                end
                S_DATA: begin
                    if (data_valid && data_ready) begin
                        if (data_is_aad != (aad_remaining != 32'd0) ||
                            valid_bytes != required_bytes) begin
                            error_status <= 1'b1;
                            match_status <= 1'b0;
                            fail_status <= 1'b0;
                            tag_record <= 128'd0;
                            payload_hold <= 128'd0;
                            hash_block <= 128'd0;
                            beat_bytes <= 5'd0;
                            scrub_index <= 9'd0;
                            state <= S_SCRUB;
                        end else if (aad_remaining != 32'd0) begin
                            hash_block <= mask_bytes(data_in, valid_bytes);
                            aad_remaining <= aad_remaining - {27'd0, valid_bytes};
                            state <= S_AAD_START;
                        end else begin
                            payload_hold <= mask_bytes(data_in, valid_bytes);
                            beat_bytes <= valid_bytes;
                            payload_remaining <= payload_remaining - {27'd0, valid_bytes};
                            state <= S_PAY_START;
                        end
                    end
                end
                S_AAD_START: begin
                    if (!gh_busy)
                        state <= S_AAD_WAIT;
                end
                S_AAD_WAIT: begin
                    if (gh_done) begin
                        hash_value <= gh_result;
                        hash_block <= 128'd0;
                        state <= S_NEXT;
                    end
                end
                S_PAY_START: begin
                    if (aes_in_ready)
                        state <= S_PAY_WAIT;
                end
                S_PAY_WAIT: begin
                    if (aes_out_valid) begin
                        payload_store[write_count] <= payload_result;
                        byte_store[write_count] <= beat_bytes;
                        write_count <= write_count + 9'd1;
                        if (decrypt_mode)
                            hash_block <= payload_hold;
                        else
                            hash_block <= payload_result;
                        payload_hold <= 128'd0;
                        beat_bytes <= 5'd0;
                        counter <= {counter[127:32], counter[31:0] + 32'd1};
                        state <= S_C_START;
                    end
                end
                S_C_START: begin
                    if (!gh_busy)
                        state <= S_C_WAIT;
                end
                S_C_WAIT: begin
                    if (gh_done) begin
                        hash_value <= gh_result;
                        hash_block <= 128'd0;
                        state <= S_NEXT;
                    end
                end
                S_LEN_START: begin
                    if (!gh_busy)
                        state <= S_LEN_WAIT;
                end
                S_LEN_WAIT: begin
                    if (gh_done) begin
                        hash_value <= gh_result;
                        state <= S_FINISH;
                    end
                end
                S_FINISH: begin
                    tag_record <= computed_tag;
                    h_value <= 128'd0;
                    tag_mask <= 128'd0;
                    hash_value <= 128'd0;
                    expected_latched <= 128'd0;
                    counter <= 128'd0;
                    payload_hold <= 128'd0;
                    hash_block <= 128'd0;
                    aad_bits <= 64'd0;
                    payload_bits <= 64'd0;
                    if (decrypt_mode && computed_tag != expected_latched) begin
                        match_status <= 1'b0;
                        fail_status <= 1'b1;
                        scrub_index <= 9'd0;
                        state <= S_SCRUB;
                    end else begin
                        match_status <= decrypt_mode;
                        fail_status <= 1'b0;
                        state <= S_TAG;
                    end
                end
                S_SCRUB: begin
                    payload_store[scrub_index] <= 128'd0;
                    byte_store[scrub_index] <= 5'd0;
                    payload_hold <= 128'd0;
                    hash_block <= 128'd0;
                    beat_bytes <= 5'd0;
                    h_value <= 128'd0;
                    j0 <= 128'd0;
                    counter <= 128'd0;
                    tag_mask <= 128'd0;
                    hash_value <= 128'd0;
                    expected_latched <= 128'd0;
                    aad_remaining <= 32'd0;
                    payload_remaining <= 32'd0;
                    aad_bits <= 64'd0;
                    payload_bits <= 64'd0;
                    write_count <= 9'd0;
                    if (scrub_index == MAX_PAYLOAD_BLOCKS - 1) begin
                        scrub_index <= 9'd0;
                        state <= S_TAG;
                    end else
                        scrub_index <= scrub_index + 9'd1;
                end
                S_TAG: begin
                    if (tag_ready) begin
                        tag_record <= 128'd0;
                        if (!fail_status && !error_status && write_count != 9'd0) begin
                            drain_index <= 9'd0;
                            state <= S_DRAIN;
                        end else begin
                            decrypt_mode <= 1'b0;
                            state <= S_IDLE;
                        end
                    end
                end
                S_DRAIN: begin
                    if (out_ready) begin
                        payload_store[drain_index] <= 128'd0;
                        byte_store[drain_index] <= 5'd0;
                        if (drain_index + 9'd1 == write_count) begin
                            drain_index <= 9'd0;
                            write_count <= 9'd0;
                            decrypt_mode <= 1'b0;
                            state <= S_IDLE;
                        end else
                            drain_index <= drain_index + 9'd1;
                    end
                end
                default: begin
                    error_status <= 1'b1;
                    match_status <= 1'b0;
                    fail_status <= 1'b0;
                    tag_record <= 128'd0;
                    scrub_index <= 9'd0;
                    state <= S_SCRUB;
                end
            endcase
        end
    end
endmodule
