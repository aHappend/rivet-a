`timescale 1ns/1ps
module tb;
    parameter integer CAPACITY = 16;
    reg clk = 0;
    reg rst_n;
    always #5 clk = !clk;
    reg key_valid = 0, key_len_sel = 0;
    reg [255:0] key_in = 0;
    wire key_ready, key_loaded;
    reg in_valid = 0, in_enc_dec = 0;
    reg [127:0] in_block = 0;
    reg [7:0] in_tag_id = 0;
    wire in_ready, out_valid;
    reg out_ready = 0;
    wire [127:0] out_block;
    wire [7:0] out_tag_id;
    wire out_enc_dec, busy, err_unloaded_key;
    reg cmd_valid = 0, cmd_decrypt = 0;
    reg [95:0] iv_in = 0;
    reg [31:0] aad_bytes = 0, payload_bytes = 0;
    reg [127:0] expected_tag = 0;
    wire cmd_ready, data_ready;
    reg data_valid = 0, data_is_aad = 0;
    reg [127:0] data_in = 0;
    reg [4:0] valid_bytes = 0;
    wire [4:0] out_valid_bytes;
    wire out_is_gcm;
    reg tag_ready = 0;
    wire tag_valid;
    wire [127:0] tag_out;
    wire tag_match, auth_fail, protocol_error;

    rivet_a2_top #(.MAX_PAYLOAD_BLOCKS(CAPACITY)) dut (
        .clk(clk), .rst_n(rst_n),
        .key_valid(key_valid), .key_ready(key_ready), .key_in(key_in),
        .key_len_sel(key_len_sel), .key_loaded(key_loaded),
        .in_valid(in_valid), .in_ready(in_ready), .in_enc_dec(in_enc_dec),
        .in_block(in_block), .in_tag_id(in_tag_id), .out_valid(out_valid),
        .out_ready(out_ready), .out_block(out_block), .out_tag_id(out_tag_id),
        .out_enc_dec(out_enc_dec), .busy(busy), .err_unloaded_key(err_unloaded_key),
        .cmd_valid(cmd_valid), .cmd_ready(cmd_ready), .cmd_decrypt(cmd_decrypt),
        .iv_in(iv_in), .aad_bytes(aad_bytes), .payload_bytes(payload_bytes),
        .expected_tag(expected_tag), .data_valid(data_valid),
        .data_ready(data_ready), .data_is_aad(data_is_aad), .data_in(data_in),
        .valid_bytes(valid_bytes), .out_valid_bytes(out_valid_bytes),
        .out_is_gcm(out_is_gcm), .tag_ready(tag_ready), .tag_valid(tag_valid),
        .tag_out(tag_out), .tag_match(tag_match), .auth_fail(auth_fail),
        .protocol_error(protocol_error)
    );

    wire [282:0] public_outputs = {
        key_ready, key_loaded, in_ready, out_valid, out_block, out_tag_id,
        out_enc_dec, busy, err_unloaded_key, cmd_ready, data_ready,
        out_valid_bytes, out_is_gcm, tag_valid, tag_out, tag_match,
        auth_fail, protocol_error
    };
    wire [143:0] payload_record = {
        out_valid, out_block, out_tag_id, out_enc_dec, out_valid_bytes, out_is_gcm
    };
    wire [131:0] tag_record = {tag_valid, tag_out, tag_match, auth_fail, protocol_error};
    reg [143:0] previous_payload;
    reg [131:0] previous_tag;
    reg stalled_payload = 0, stalled_tag = 0;
    reg gcm_active = 0, release_ok = 0, tag_seen = 0;
    reg status_hold = 0;
    reg [2:0] retired_status = 0;
    integer cycles = 0, raw_checks = 0, tag_checks = 0, payload_checks = 0;
    integer key_checks = 0, reset_checks = 0, error_checks = 0, beat_checks = 0;
    integer payload_transfers = 0, tag_transfers = 0;
    integer case_id = 0;
    integer command_cycle = 0, last_tag_latency = 0, failure_latency = -1;

    task automatic fail(input string message);
        $display("ASSERT case=%0d cycle=%0d time=%0t %s", case_id, cycles, $time, message);
        $fatal(1);
    endtask

    task automatic check_public;
        begin
            if ((^public_outputs) === 1'bx) fail("PUBLIC_XZ");
            if (!rst_n) begin
                if (public_outputs !== 0) fail("RESET_OUTPUT_NONZERO");
            end else begin
                if (err_unloaded_key !== 0) fail("UNLOADED_STATUS");
                if (!out_valid && payload_record !== 0) fail("INACTIVE_PLAINTEXT");
                if (!tag_valid && tag_out !== 0) fail("INACTIVE_TAG");
                if (gcm_active && !tag_seen && out_valid)
                    fail("PREAUTH_RELEASE");
                if (busy && (key_ready || in_ready || cmd_ready))
                    fail("BUSY_ADMISSION");
                if (tag_valid && (!busy || out_valid))
                    fail("TAG_PHASE");
                if (key_valid && (in_ready || cmd_ready))
                    fail("KEY_PRIORITY");
                if (cmd_valid && in_ready) fail("COMMAND_PRIORITY");
                if (status_hold && {tag_match, auth_fail, protocol_error} !== retired_status)
                    fail("RETIRED_STATUS_CHANGED");
            end
        end
    endtask

    always @(posedge clk) begin
        check_public();
        cycles = cycles + 1;
        if (!rst_n) begin
            stalled_payload = 0;
            stalled_tag = 0;
            tag_seen = 0;
            status_hold = 0;
        end else begin
            if ((key_valid && key_ready) || (cmd_valid && cmd_ready) ||
                (in_valid && in_ready)) status_hold = 0;
            if (stalled_payload && payload_record !== previous_payload)
                fail("PAYLOAD_STALL_UNSTABLE");
            if (stalled_tag && tag_record !== previous_tag)
                fail("TAG_STALL_UNSTABLE");
            if (out_valid && out_ready) payload_transfers = payload_transfers + 1;
            if (tag_valid && tag_ready) begin
                tag_transfers = tag_transfers + 1;
                if (release_ok) tag_seen = 1;
                status_hold = 1;
                retired_status = {tag_match, auth_fail, protocol_error};
            end
            previous_payload = payload_record;
            previous_tag = tag_record;
            stalled_payload = out_valid && !out_ready;
            stalled_tag = tag_valid && !tag_ready;
        end
        #1;
        check_public();
    end
    always @(negedge clk) check_public();

    task automatic tick;
        begin @(posedge clk); #2; @(negedge clk); #1; end
    endtask

    task automatic quiet(input integer n);
        integer j;
        begin
            for (j = 0; j < n; j = j + 1) begin
                if (out_valid || tag_valid) fail("UNEXPECTED_RECORD");
                tick();
            end
        end
    endtask

    task automatic reset_dut;
        begin
            // Mid-cycle assertion is intentionally independent of a clock edge.
            #1;
            rst_n = 0;
            key_valid = 0; in_valid = 0; cmd_valid = 0; data_valid = 0;
            out_ready = 0; tag_ready = 0;
            gcm_active = 0; release_ok = 0;
            #1;
            check_public();
            tick(); tick();
            rst_n = 1;
            #1;
            if (key_ready || cmd_ready || in_ready) fail("RESET_RELEASE_EARLY_READY");
            tick();
            if (!key_ready || key_loaded || in_ready || cmd_ready || busy)
                fail("RESET_IDLE");
            reset_checks = reset_checks + 1;
        end
    endtask

    task automatic wait_idle;
        integer n;
        begin
            n = 0;
            while (busy || !key_ready) begin
                tick(); n = n + 1;
                if (n > 1000) fail("IDLE_PROGRESS");
            end
            if (out_valid || tag_valid) fail("IDLE_RECORD");
        end
    endtask

    task automatic load_key(input [255:0] k, input bit long_key, input bit priority_test);
        integer j, duration;
        begin
            wait_idle();
            key_in = k; key_len_sel = long_key; key_valid = 1;
            in_valid = priority_test; cmd_valid = priority_test;
            #1;
            if (!key_ready || in_ready || cmd_ready) fail("KEY_ARBITRATION");
            tick();
            key_valid = 0; cmd_valid = 0; in_valid = 0;
            key_in = ~k; key_len_sel = !long_key;
            if (key_loaded || !busy) fail("KEY_LOAD_EDGE");
            duration = long_key ? 52 : 40;
            for (j = 1; j <= duration; j = j + 1) begin
                tick();
                if (key_loaded !== (j == duration)) fail("KEY_EXPANSION_LATENCY");
            end
            wait_idle();
            if (!key_loaded) fail("KEY_NOT_PERSISTENT");
            if ({tag_match, auth_fail, protocol_error} !== 0) fail("KEY_STATUS_CLEAR");
            key_checks = key_checks + 1;
        end
    endtask

    task automatic raw_start(input [127:0] b, input bit dec, input [7:0] id);
        begin
            wait_idle();
            gcm_active = 0;
            in_block = b; in_enc_dec = dec; in_tag_id = id; in_valid = 1;
            #1;
            if (!in_ready) fail("RAW_NOT_READY");
            tick(); in_valid = 0;
            in_block = ~b; in_enc_dec = !dec; in_tag_id = ~id;
            if (out_valid || !busy) fail("RAW_ACCEPT_TIMELINE");
            if ({tag_match, auth_fail, protocol_error} !== 0) fail("RAW_STATUS_CLEAR");
        end
    endtask

    task automatic raw_result(input [127:0] expected, input bit dec,
                              input [7:0] id, input integer rounds);
        integer j, before_count;
        begin
            for (j = 1; j <= rounds; j = j + 1) begin
                tick();
                if (out_valid !== (j == rounds)) fail("RAW_ROUND_LATENCY");
            end
            if (out_block !== expected || out_tag_id !== id ||
                out_enc_dec !== dec || out_valid_bytes !== 16 || out_is_gcm !== 0)
                fail("AES_RESULT");
            repeat (4) tick();
            before_count = payload_transfers;
            out_ready = 1;
            if (in_ready || key_ready || cmd_ready) fail("RAW_REPLACEMENT");
            tick(); out_ready = 0;
            if (payload_transfers != before_count + 1 || out_valid)
                fail("RAW_TRANSFER_COUNT");
            raw_checks = raw_checks + 1;
            quiet(2);
        end
    endtask

    task automatic command(input bit dec, input [95:0] iv,
                           input [31:0] an, input [31:0] pn,
                           input [127:0] expected, input bit success);
        begin
            wait_idle();
            gcm_active = 1; tag_seen = 0; release_ok = success;
            cmd_decrypt = dec; iv_in = iv; aad_bytes = an; payload_bytes = pn;
            expected_tag = expected; cmd_valid = 1; in_valid = 1;
            #1;
            if (!cmd_ready || in_ready || !key_loaded) fail("COMMAND_ARBITRATION");
            tick(); cmd_valid = 0; in_valid = 0;
            command_cycle = cycles;
            cmd_decrypt = !dec; iv_in = ~iv; aad_bytes = ~an; payload_bytes = ~pn;
            expected_tag = ~expected;
            if (!busy || out_valid || tag_valid || data_ready)
                fail("COMMAND_ACCEPT_TIMELINE");
            if ({tag_match, auth_fail, protocol_error} !== 0 && pn <= 16*CAPACITY)
                fail("COMMAND_STATUS_CLEAR");
        end
    endtask

    task automatic wait_data;
        integer n;
        begin
            n = 0;
            while (!data_ready) begin
                if (tag_valid) fail("UNEXPECTED_EARLY_TAG");
                tick(); n = n + 1;
                if (n > 2000) fail("DATA_PROGRESS");
            end
        end
    endtask

    task automatic beat(input bit aad, input [127:0] value,
                        input [4:0] count, input integer gap);
        integer j;
        begin
            wait_data();
            for (j = 0; j < gap; j = j + 1) tick();
            data_is_aad = aad; data_in = value; valid_bytes = count; data_valid = 1;
            #1;
            if (!data_ready) fail("BEAT_NOT_ACCEPTED");
            tick(); data_valid = 0;
            data_in = ~value; valid_bytes = 0; data_is_aad = !aad;
            if (data_ready) fail("BEAT_ACCEPT_TIMELINE");
            data_valid = 1;
            tick();
            data_valid = 0;
            beat_checks = beat_checks + 1;
        end
    endtask

    task automatic tag_result(input [127:0] expected, input bit match_value,
                              input bit fail_value, input bit error_value,
                              input integer nblocks, input bit dec);
        integer n, before_count;
        reg [131:0] saved;
        begin
            n = 0;
            while (!tag_valid) begin
                tick(); n = n + 1;
                if (n > 3000 + 200*CAPACITY) fail("TAG_PROGRESS");
            end
            last_tag_latency = cycles - command_cycle;
            $display("TAG_TIMELINE case=%0d command=%0d presentation=%0d latency=%0d",
                     case_id, command_cycle, cycles, last_tag_latency);
            if (tag_out !== expected || tag_match !== match_value ||
                auth_fail !== fail_value || protocol_error !== error_value) begin
                $display("TAG observed=%032h expected=%032h status=%b%b%b expected=%b%b%b",
                         tag_out, expected, tag_match, auth_fail, protocol_error,
                         match_value, fail_value, error_value);
                fail("TAG_RESULT");
            end
            saved = tag_record;
            // Unaccepted requests/stream must not disturb the pending result.
            in_valid = 1; cmd_valid = 1; key_valid = 1; data_valid = 1;
            repeat (7) begin
                tick();
                if (tag_record !== saved || data_ready) fail("TAG_STALL");
            end
            in_valid = 0; cmd_valid = 0; key_valid = 0; data_valid = 0;
            before_count = tag_transfers;
            tag_ready = 1;
            if (key_ready || cmd_ready || in_ready || out_valid) fail("TAG_REPLACEMENT");
            tick(); tag_ready = 0;
            if (tag_transfers != before_count + 1 || tag_valid) fail("TAG_TRANSFER_COUNT");
            if (nblocks != 0) begin
                if (!out_valid || !out_is_gcm || out_enc_dec !== dec)
                    fail("FIRST_RELEASE_TIMELINE");
            end else if (out_valid) fail("FAILURE_OR_EMPTY_RELEASE");
            tag_checks = tag_checks + 1;
            if (error_value) error_checks = error_checks + 1;
        end
    endtask

    task automatic payload_result(input [127:0] expected, input [4:0] count,
                                  input bit dec, input bit last, input integer stall);
        integer j, before_count;
        begin
            if (!out_valid || !tag_seen) fail("MISSING_AUTHENTICATED_RESULT");
            if (out_block !== expected || out_valid_bytes !== count ||
                out_tag_id !== 0 || out_is_gcm !== 1 || out_enc_dec !== dec)
                fail("GCM_PAYLOAD_RESULT");
            for (j = 0; j < stall; j = j + 1) tick();
            before_count = payload_transfers;
            out_ready = 1;
            if (key_ready || cmd_ready || in_ready) fail("DRAIN_REPLACEMENT");
            tick(); out_ready = 0;
            if (payload_transfers != before_count + 1) fail("PAYLOAD_TRANSFER_COUNT");
            if (last && (out_valid || busy)) fail("LAST_RELEASE_TIMELINE");
            payload_checks = payload_checks + 1;
        end
    endtask

    initial begin
        // This is the required time-zero assertion, with no preceding reset toggle.
        rst_n = 0;
        #0;
        #1;
        check_public();
        @(posedge clk); // The always block checks Active-region outputs at t=5.
        #2;
        @(negedge clk); #1;
        reset_dut();
        `include "stimulus.svh"
        $display("COUNTS cycles=%0d keys=%0d raw=%0d tags=%0d payload=%0d beats=%0d resets=%0d errors=%0d",
                 cycles, key_checks, raw_checks, tag_checks, payload_checks,
                 beat_checks, reset_checks, error_checks);
        $display("SIMULATION_COMPLETE");
        $finish;
    end
endmodule
