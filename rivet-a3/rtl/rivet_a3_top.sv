module rivet_a3_top #(
    parameter integer MAX_PAYLOAD_BLOCKS = 16
) (
    input wire clk, rst_n,
    input wire key_valid,
    output wire key_ready,
    input wire [255:0] key_in,
    input wire key_len_sel,
    output wire key_loaded,
    input wire in_valid,
    output wire in_ready,
    input wire in_enc_dec,
    input wire [127:0] in_block,
    input wire [7:0] in_tag_id,
    output wire out_valid,
    input wire out_ready,
    output wire [127:0] out_block,
    output wire [7:0] out_tag_id,
    output wire out_enc_dec,
    output wire busy, err_unloaded_key,
    input wire cmd_valid,
    output wire cmd_ready,
    input wire cmd_decrypt,
    input wire [95:0] iv_in,
    input wire [31:0] aad_bytes, payload_bytes,
    input wire [127:0] expected_tag,
    input wire data_valid,
    output wire data_ready,
    input wire data_is_aad,
    input wire [127:0] data_in,
    input wire [4:0] valid_bytes,
    output wire [4:0] out_valid_bytes,
    output wire out_is_gcm,
    input wire tag_ready,
    output wire tag_valid,
    output wire [127:0] tag_out,
    output wire tag_match, auth_fail, protocol_error,
    input wire [1:0] key_slot_id,
    input wire key_lock,
    output wire key_result_valid,
    input wire key_result_ready,
    output wire [3:0] key_result_code,
    input wire task_valid,
    output wire task_ready,
    input wire [511:0] task_descriptor,
    input wire dma_submit_valid,
    output wire dma_submit_ready,
    input wire [31:0] dma_desc_addr,
    input wire dma_priority,
    input wire [7:0] dma_cookie,
    output wire completion_valid,
    input wire completion_ready,
    output wire [7:0] completion_cookie,
    output wire [1:0] completion_ctx_id,
    output wire [3:0] completion_code,
    output wire completion_final,
    output wire [127:0] completion_tag,
    output wire mem_req_valid,
    input wire mem_req_ready,
    output wire mem_req_write,
    output wire [31:0] mem_req_addr,
    output wire [127:0] mem_req_wdata,
    output wire [15:0] mem_req_wstrb,
    input wire mem_rsp_valid,
    output wire mem_rsp_ready,
    input wire [127:0] mem_rsp_rdata,
    input wire mem_rsp_error,
    input wire csr_valid,
    output wire csr_ready,
    input wire csr_write,
    input wire [7:0] csr_addr,
    input wire [31:0] csr_wdata,
    output wire csr_rsp_valid,
    input wire csr_rsp_ready,
    output wire [31:0] csr_rdata,
    output wire csr_error
);
    localparam integer CAP = (MAX_PAYLOAD_BLOCKS>=1 && MAX_PAYLOAD_BLOCKS<=256)
                             ? 16*MAX_PAYLOAD_BLOCKS : 16;
    generate
        if (MAX_PAYLOAD_BLOCKS<1 || MAX_PAYLOAD_BLOCKS>256) begin : g_illegal
            initial $fatal(1,"PARAMETER ERROR: MAX_PAYLOAD_BLOCKS must be 1..256");
        end
    endgenerate
    localparam IDLE=0, VALIDATE=1, LOAD_KEY=2, KEY_WAIT=3,
        H_START=4, H_WAIT=5, MASK_START=6, MASK_WAIT=7, NEXT=8,
        GET_BEAT=9, READ_REQ=10, READ_RSP=11, BYTE=12,
        CTR_START=13, CTR_WAIT=14, ECB_START=15, ECB_WAIT=16,
        GH_START=17, GH_WAIT=18, LENGTH=19, FINALIZE=20,
        SAVE=21, RESULT=22, WAIT_RETIRE=23, TAG=24,
        DRAIN=25, WRITE_REQ=26, WRITE_RSP=27, SCRUB=28,
        CLEAR=29, RAW_START=30, RAW_WAIT=31, RAW_OUT=32, FAULT_ACK=33;
    reg [5:0] state, gh_return;
    reg awake, legacy, raw_job, dma_job, first_fragment, last_fragment;
    reg [511:0] descriptor;
    reg [31:0] descriptor_addr;
    reg [1:0] ctx_id, selected_slot;
    reg [1279:0] work;
    reg [3:0] live_mask;
    reg [1:0] bindings [0:3];
    reg [7:0] payload_store [0:4*CAP-1];
    reg [31:0] destination_store [0:4*CAP-1];
    reg [31:0] aad_remaining, payload_remaining, aad_total, payload_total;
    reg [31:0] aad_addr, src_addr, dst_addr;
    reg [127:0] expected_latched, beat_hold, ecb_block, aes_block, hash_block;
    reg [4:0] beat_left, ecb_count;
    reg [7:0] current_byte, raw_tag;
    reg direction;
    reg [1:0] output_mode;
    reg [12:0] retained_count, drain_index, scrub_index;
    reg [3:0] result_code_reg;
    reg [127:0] result_tag_reg;
    reg [31:0] result_bytes_reg;
    reg match_status, fail_status, protocol_status;
    reg abort_job, error_scrub, scrub_to_result;
    reg owns_session, scrub_to_fault;
    reg status_allowed;
    reg [31:0] sticky_errors;
    reg csr_pending, csr_bad;
    reg [31:0] csr_data;
    reg abort_pending;
    reg [1:0] abort_id;
    wire visible = rst_n && awake;
    wire [1:0] mode = work[2:1];
    wire decrypt = work[3];
    wire [127:0] accumulator = work[231:104];
    wire [127:0] h_value = work[359:232];
    wire [127:0] tag_mask = work[487:360];
    wire [127:0] counter = work[615:488];
    wire [63:0] aad_bits = work[679:616];
    wire [63:0] data_bits = work[743:680];
    wire [127:0] pending_hash = work[871:744];
    wire [4:0] pending_count = work[876:872];
    wire [127:0] keystream = work[1004:877];
    wire [4:0] keystream_count = work[1009:1005];
    wire [12:0] stored_count = work[1022:1010];
    wire [1:0] d_mode = descriptor[1:0];
    wire d_decrypt = descriptor[2];
    wire [1:0] d_ctx = descriptor[4:3];
    wire [1:0] d_slot = descriptor[6:5];
    wire d_first = descriptor[7], d_last = descriptor[8];
    wire [31:0] d_aad = descriptor[160+:32];
    wire [31:0] d_payload = descriptor[192+:32];
    wire [31:0] d_aad_addr = descriptor[32+:32];
    wire [31:0] d_src = descriptor[64+:32];
    wire [31:0] d_dst = descriptor[96+:32];
    wire [31:0] d_status = descriptor[128+:32];
    wire [95:0] d_iv;
    wire [127:0] d_tag;
    genvar b;
    generate for(b=0;b<12;b=b+1) begin : g_iv
        assign d_iv[95-8*b-:8]=descriptor[8*(28+b)+:8];
    end
    for(b=0;b<16;b=b+1) begin : g_tag
        assign d_tag[127-8*b-:8]=descriptor[8*(40+b)+:8];
    end endgenerate
    wire [1279:0] context_read;
    wire [1:0] context_read_id = ctx_id;
    wire context_write = visible && state==SAVE;
    wire context_clear = visible && state==CLEAR;
    wire [1:0] context_clear_id = abort_job ? abort_id : ctx_id;
    wire kt_ready;
    wire [3:0] valid_mask, lock_mask;
    reg [3:0] bound_mask;
    wire [255:0] selected_key;
    wire selected_key_len;
    wire scheduler_queued, scheduler_active, scheduler_retire;
    wire scheduler_fault;
    wire [3:0] scheduler_event;
    wire dispatch_valid, dispatch_ready, dispatch_dma;
    wire [511:0] dispatch_descriptor;
    wire [7:0] dispatch_cookie;
    wire [31:0] dispatch_desc_addr;
    wire result_ready;
    wire io_ready, io_rsp_valid, io_error;
    wire [7:0] io_rbyte;
    wire csr_abort_request = csr_valid && csr_ready && csr_write &&
                            csr_addr==8'h14 && csr_wdata[31:2]==0;
    wire key_window = visible && state==IDLE && !scheduler_active &&
                      !abort_pending && !csr_abort_request;
    assign key_ready = key_window && kt_ready;
    wire key_transfer = key_valid && key_ready;
    wire select_enable = visible && state==IDLE && !key_transfer &&
                         !abort_pending && !csr_abort_request;
    assign dispatch_ready = select_enable;
    wire legacy_window = select_enable && !scheduler_active &&
                         !scheduler_queued && !task_valid;
    assign cmd_ready = legacy_window && valid_mask[0];
    assign in_ready = legacy_window && !cmd_valid && valid_mask[0];
    assign err_unloaded_key = legacy_window && !valid_mask[0] && (cmd_valid || in_valid);
    assign key_loaded = visible && valid_mask[0];
    assign busy = visible && (state!=IDLE || scheduler_active || scheduler_queued ||
                              abort_pending || key_result_valid);
    assign data_ready = visible && state==GET_BEAT;
    assign tag_valid = visible && state==TAG;
    assign tag_out = tag_valid ? result_tag_reg : 128'd0;
    assign tag_match = visible && match_status;
    assign auth_fail = visible && fail_status;
    assign protocol_error = visible && protocol_status;
    assign csr_ready = visible && !csr_pending && !abort_pending;
    assign csr_rsp_valid = visible && csr_pending;
    assign csr_rdata = csr_rsp_valid ? csr_data : 32'd0;
    assign csr_error = csr_rsp_valid && csr_bad;
    wire [31:0] remaining_section = aad_remaining!=0 ? aad_remaining : payload_remaining;
    wire [4:0] required_bytes = remaining_section>=16 ? 5'd16 : remaining_section[4:0];
    wire [12:0] remaining_output = retained_count-drain_index;
    wire [4:0] drain_bytes = remaining_output>=16 ? 5'd16 : remaining_output[4:0];
    reg [127:0] drain_block;
    integer i, j;
    always @* begin
        bound_mask=0;
        for(j=0;j<4;j=j+1)
            if(live_mask[j]) bound_mask[bindings[j]]=1'b1;
        drain_block=0;
        for(j=0;j<16;j=j+1)
            if(j<drain_bytes && drain_index+j<CAP)
                drain_block[127-8*j-:8]=payload_store[ctx_id*CAP+drain_index+j];
    end
    wire aes_out_valid, aes_in_ready, aes_key_ready, aes_loaded, aes_busy;
    wire [127:0] aes_out_block;
    wire [7:0] aes_out_tag;
    wire aes_out_mode;
    wire crypto_keep = visible && state!=IDLE && state!=RESULT &&
        state!=WAIT_RETIRE && state!=TAG && state!=DRAIN &&
        state!=WRITE_REQ && state!=WRITE_RSP && state!=SCRUB && state!=CLEAR &&
        state!=FAULT_ACK;
    wire crypto_rst_n = rst_n && crypto_keep;
    wire aes_start = visible && (state==RAW_START || state==H_START ||
        state==MASK_START || state==CTR_START || state==ECB_START);
    wire [127:0] aes_input = state==H_START ? 128'd0 :
        state==MASK_START ? {work[103:8],32'd1} :
        state==CTR_START ? counter : aes_block;
    wire aes_direction = (state==RAW_START || state==ECB_START) && direction;
    wire aes_take = state==H_WAIT || state==MASK_WAIT || state==CTR_WAIT ||
                    state==ECB_WAIT || state==RAW_WAIT;
    assign out_valid = visible && (state==RAW_OUT || (state==DRAIN && retained_count!=0));
    assign out_block = !out_valid ? 128'd0 : state==RAW_OUT ? aes_block : drain_block;
    assign out_tag_id = out_valid && state==RAW_OUT ? raw_tag : 8'd0;
    assign out_enc_dec = out_valid && direction;
    assign out_valid_bytes = !out_valid ? 5'd0 : state==RAW_OUT ? 5'd16 : drain_bytes;
    assign out_is_gcm = out_valid && state==DRAIN && output_mode==2;
    wire gh_busy, gh_done;
    wire [127:0] gh_result;
    wire io_valid = visible && (state==READ_REQ || state==WRITE_REQ);
    wire io_write = state==WRITE_REQ;
    wire [31:0] io_addr = state==WRITE_REQ ?
        destination_store[ctx_id*CAP+drain_index] :
        aad_remaining!=0 ? aad_addr+(aad_total-aad_remaining) :
                           src_addr+(payload_total-payload_remaining);
    wire [7:0] io_wbyte = state==WRITE_REQ ?
        payload_store[ctx_id*CAP+drain_index] : 8'd0;
    wire io_rsp_ready = visible && (state==READ_RSP || state==WRITE_RSP);
    rivet_a3_key_table u_key_table (
        .clk(clk),.rst_n(rst_n),.load_valid(key_transfer),.load_ready(kt_ready),
        .slot_id(key_slot_id),.key_in(key_in),.key_len_sel(key_len_sel),
        .lock_in(key_lock),.bound_mask(bound_mask),
        .result_valid(key_result_valid),.result_ready(key_result_ready),
        .result_code(key_result_code),.read_slot_id(selected_slot),
        .read_key(selected_key),.read_key_len(selected_key_len),
        .valid_mask(valid_mask),.lock_mask(lock_mask)
    );
    rivet_a3_context_store u_context_store (
        .clk(clk),.rst_n(rst_n),.write_en(context_write),.write_id(ctx_id),
        .write_data(work),.read_id(context_read_id),.read_data(context_read),
        .clear_en(context_clear),.clear_id(context_clear_id)
    );
    rivet_a3_aes_core u_aes_core (
        .clk(clk),.rst_n(crypto_rst_n),.key_valid(state==LOAD_KEY && visible),
        .key_ready(aes_key_ready),.key_in(selected_key),.key_len_sel(selected_key_len),
        .key_loaded(aes_loaded),.in_valid(aes_start),.in_ready(aes_in_ready),
        .in_enc_dec(aes_direction),.in_block(aes_input),.in_tag_id(raw_tag),
        .out_valid(aes_out_valid),.out_ready(aes_take),.out_block(aes_out_block),
        .out_tag_id(aes_out_tag),.out_enc_dec(aes_out_mode),.busy(aes_busy)
    );
    rivet_a3_ghash u_ghash (
        .clk(clk),.rst_n(crypto_rst_n),.clear(state==LOAD_KEY),
        .start(state==GH_START && visible),.x(accumulator^hash_block),
        .h(h_value),.busy(gh_busy),.done(gh_done),.result(gh_result)
    );
    rivet_a3_scheduler_dma u_scheduler_dma (
        .clk(clk),.rst_n(rst_n),.enable(select_enable),
        .task_valid(task_valid),.task_ready(task_ready),.task_descriptor(task_descriptor),
        .dma_submit_valid(dma_submit_valid),.dma_submit_ready(dma_submit_ready),
        .dma_desc_addr(dma_desc_addr),.dma_priority(dma_priority),.dma_cookie(dma_cookie),
        .completion_valid(completion_valid),.completion_ready(completion_ready),
        .completion_cookie(completion_cookie),.completion_ctx_id(completion_ctx_id),
        .completion_code(completion_code),.completion_final(completion_final),
        .completion_tag(completion_tag),.mem_req_valid(mem_req_valid),
        .mem_req_ready(mem_req_ready),.mem_req_write(mem_req_write),
        .mem_req_addr(mem_req_addr),.mem_req_wdata(mem_req_wdata),
        .mem_req_wstrb(mem_req_wstrb),.mem_rsp_valid(mem_rsp_valid),
        .mem_rsp_ready(mem_rsp_ready),.mem_rsp_rdata(mem_rsp_rdata),
        .mem_rsp_error(mem_rsp_error),.dispatch_valid(dispatch_valid),
        .dispatch_ready(dispatch_ready),.dispatch_descriptor(dispatch_descriptor),
        .dispatch_dma(dispatch_dma),.dispatch_cookie(dispatch_cookie),
        .dispatch_desc_addr(dispatch_desc_addr),.result_valid(state==RESULT && visible),
        .result_ready(result_ready),.result_code(result_code_reg),
        .result_ctx_id(ctx_id),.result_final(last_fragment),.result_tag(result_tag_reg),
        .result_bytes(result_bytes_reg),.result_status_allowed(status_allowed),
        .io_valid(io_valid),.io_ready(io_ready),
        .io_write(io_write),.io_addr(io_addr),.io_wbyte(io_wbyte),
        .io_rsp_valid(io_rsp_valid),.io_rsp_ready(io_rsp_ready),
        .io_rbyte(io_rbyte),.io_error(io_error),.queued(scheduler_queued),
        .active(scheduler_active),.fault_valid(scheduler_fault),
        .fault_ready(state==FAULT_ACK && visible),
        .retire(scheduler_retire),.event_code(scheduler_event)
    );

    function automatic overlaps(input [31:0] a, input [32:0] an,
                                 input [31:0] c, input [32:0] cn);
        begin
            overlaps = an!=0 && cn!=0 && {1'b0,a}<({1'b0,c}+cn) &&
                       {1'b0,c}<({1'b0,a}+an);
        end
    endfunction
    function automatic range_bad(input [31:0] address, input [31:0] count);
        begin
            range_bad = count!=0 && ({1'b0,address}+{1'b0,count})>33'h100000000;
        end
    endfunction
    wire [63:0] saved_aad = d_first ? 64'd0 : context_read[679:616];
    wire [63:0] saved_data = d_first ? 64'd0 : context_read[743:680];
    wire [12:0] saved_count = d_first ? 13'd0 : context_read[1022:1010];
    wire [64:0] new_aad_bits = {1'b0,saved_aad}+({33'd0,d_aad}<<3);
    wire [64:0] new_data_bits = {1'b0,saved_data}+({33'd0,d_payload}<<3);
    wire [4:0] saved_stream = d_first ? 5'd0 : context_read[1009:1005];
    wire [32:0] counter_blocks = d_payload>saved_stream ?
        ({1'b0,d_payload}-{28'd0,saved_stream}+33'd15)>>4 : 33'd0;
    wire [31:0] saved_counter = d_first ? (d_mode==2 ? 32'd2 : 32'd1) :
                                              context_read[519:488];
    wire [32:0] counters_available = (!d_first && context_read[1023]) ?
        33'd0 : 33'h100000000-{1'b0,saved_counter};
    wire status_range_safe = d_status[3:0]==0 && d_status<=32'hffffffe0 &&
        !overlaps(d_status,33'd32,d_aad_addr,{1'b0,d_aad}) &&
        !overlaps(d_status,33'd32,d_src,{1'b0,d_payload}) &&
        !overlaps(d_status,33'd32,d_dst,{1'b0,d_payload});
    reg [3:0] validation_code;
    always @* begin
        validation_code=0;
        if(descriptor[31:9]!=0 || descriptor[511:456]!=0 || d_mode==3)
            validation_code=1;
        else if(!valid_mask[d_slot]) validation_code=2;
        else if(d_first && context_read[0]) validation_code=4;
        else if(!d_first && (!context_read[0] || context_read[2:1]!=d_mode ||
            context_read[3]!=d_decrypt || context_read[4]!=dma_job ||
            context_read[6:5]!=d_slot || context_read[103:8]!=d_iv))
            validation_code=4;
        else if(d_mode!=2 && (!d_first || !d_last || d_aad!=0))
            validation_code=1;
        else if(!d_first && context_read[7] && d_aad!=0) validation_code=4;
        else if((d_mode==0 && d_payload[3:0]!=0) ||
                ({20'd0,saved_count}+{1'b0,d_payload})>CAP ||
                new_aad_bits[64] || new_data_bits[64] ||
                (d_mode!=0 && counter_blocks>counters_available))
            validation_code=5;
        else if(dma_job && (d_status[3:0]!=0 || d_status>32'hffffffe0 ||
            range_bad(d_aad_addr,d_aad) || range_bad(d_src,d_payload) ||
            range_bad(d_dst,d_payload) ||
            (d_src!=d_dst && overlaps(d_src,{1'b0,d_payload},d_dst,{1'b0,d_payload})) ||
            overlaps(d_aad_addr,{1'b0,d_aad},d_dst,{1'b0,d_payload}) ||
            overlaps(descriptor_addr,33'd64,d_aad_addr,{1'b0,d_aad}) ||
            overlaps(descriptor_addr,33'd64,d_src,{1'b0,d_payload}) ||
            overlaps(descriptor_addr,33'd64,d_dst,{1'b0,d_payload}) ||
            overlaps(d_status,33'd32,d_aad_addr,{1'b0,d_aad}) ||
            overlaps(d_status,33'd32,d_src,{1'b0,d_payload}) ||
            overlaps(d_status,33'd32,d_dst,{1'b0,d_payload})))
            validation_code=1;
    end
    wire [7:0] transformed_byte = current_byte^keystream[127:120];
    reg [127:0] appended_hash, appended_ecb;
    always @* begin
        appended_hash=pending_hash;
        appended_hash[127-8*pending_count-:8] =
            aad_remaining!=0 ? current_byte : decrypt ? current_byte : transformed_byte;
        appended_ecb=ecb_block;
        appended_ecb[127-8*ecb_count-:8]=current_byte;
    end
    reg [511:0] legacy_descriptor;
    integer k;
    always @* begin
        legacy_descriptor=0;
        legacy_descriptor[8:0]={1'b1,1'b1,2'd0,2'd0,cmd_decrypt,2'd2};
        legacy_descriptor[160+:32]=aad_bytes;
        legacy_descriptor[192+:32]=payload_bytes;
        for(k=0;k<12;k=k+1)
            legacy_descriptor[8*(28+k)+:8]=iv_in[95-8*k-:8];
        for(k=0;k<16;k=k+1)
            legacy_descriptor[8*(40+k)+:8]=expected_tag[127-8*k-:8];
    end

    wire [31:0] w1c = csr_valid && csr_ready && csr_write &&
        csr_addr==8'h10 && (csr_wdata & ~32'h000001fe)==0 ? csr_wdata : 32'd0;
    reg [3:0] current_error;
    reg current_csr_error;
    always @* begin
        current_error=0;
        case(state)
            VALIDATE: current_error=validation_code;
            GET_BEAT: if(data_valid &&
                (data_is_aad!=(aad_remaining!=0) || valid_bytes!=required_bytes))
                current_error=6;
            READ_RSP, WRITE_RSP: if(io_rsp_valid && io_error) current_error=8;
            FINALIZE: if(mode==2 && decrypt &&
                         (tag_mask^accumulator)!=expected_latched) current_error=7;
            WAIT_RETIRE: if(scheduler_fault) current_error=8;
            default: begin end
        endcase
        current_csr_error=0;
        if(csr_valid && csr_ready) begin
            case(csr_addr)
                8'h00,8'h04,8'h08,8'h0c: current_csr_error=csr_write;
                8'h10: current_csr_error=csr_write &&
                                              (csr_wdata & ~32'h000001fe)!=0;
                8'h14: current_csr_error=!csr_write || csr_wdata[31:2]!=0 ||
                    state!=IDLE || scheduler_active || scheduler_queued ||
                    key_result_valid || key_transfer;
                default: current_csr_error=1;
            endcase
        end
    end
    wire [31:0] error_bits = (current_error!=0 ? 32'd1<<current_error : 32'd0) |
        (current_csr_error ? 32'd2 : 32'd0) |
        (scheduler_event!=0 ? 32'd1<<scheduler_event : 32'd0) |
        ((key_transfer && (lock_mask[key_slot_id] || bound_mask[key_slot_id])) ?
          32'd8 : 32'd0);
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            awake<=0; state<=IDLE; gh_return<=0;
            legacy<=0; raw_job<=0; dma_job<=0;
            first_fragment<=0; last_fragment<=0; descriptor<=0; descriptor_addr<=0;
            ctx_id<=0; selected_slot<=0; work<=0; live_mask<=0;
            aad_remaining<=0; payload_remaining<=0; aad_total<=0; payload_total<=0;
            aad_addr<=0; src_addr<=0; dst_addr<=0;
            expected_latched<=0; beat_hold<=0; ecb_block<=0; aes_block<=0; hash_block<=0;
            beat_left<=0; ecb_count<=0; current_byte<=0; raw_tag<=0; direction<=0;
            output_mode<=0; retained_count<=0; drain_index<=0; scrub_index<=0;
            result_code_reg<=0; result_tag_reg<=0; result_bytes_reg<=0;
            match_status<=0; fail_status<=0; protocol_status<=0;
            abort_job<=0; error_scrub<=0; scrub_to_result<=0;
            owns_session<=0; scrub_to_fault<=0;
            status_allowed<=0;
            sticky_errors<=0; csr_pending<=0; csr_bad<=0; csr_data<=0;
            abort_pending<=0; abort_id<=0;
            for(i=0;i<4;i=i+1) bindings[i]<=0;
            for(i=0;i<4*CAP;i=i+1) begin
                payload_store[i]<=0; destination_store[i]<=0;
            end
        end else begin
            awake<=1;
            if(awake) begin
                sticky_errors<=(sticky_errors & ~w1c) | error_bits;
                if(csr_pending && csr_rsp_ready) begin
                    csr_pending<=0; csr_data<=0; csr_bad<=0;
                end
                if(csr_valid && csr_ready) begin
                    csr_pending<=1; csr_bad<=0; csr_data<=0;
                    case(csr_addr)
                        8'h00: if(csr_write) begin csr_bad<=1; end
                               else csr_data<=32'h52415633;
                        8'h04: if(csr_write) begin csr_bad<=1; end
                               else csr_data<={31'd0,busy};
                        8'h08: if(csr_write) begin csr_bad<=1; end
                               else csr_data<={24'd0,lock_mask,valid_mask};
                        8'h0c: if(csr_write) begin csr_bad<=1; end
                               else csr_data<={28'd0,live_mask};
                        8'h10: if(csr_write) begin
                                   if((csr_wdata & ~32'h000001fe)!=0) begin
                                       csr_bad<=1;
                                   end
                               end else csr_data<=sticky_errors;
                        8'h14: begin
                            if(!csr_write || csr_wdata[31:2]!=0 ||
                               state!=IDLE || scheduler_active || scheduler_queued ||
                               key_result_valid || key_transfer) begin
                                csr_bad<=1;
                            end else begin
                                abort_pending<=1; abort_id<=csr_wdata[1:0];
                                csr_pending<=0;
                            end
                        end
                        default: begin csr_bad<=1; end
                    endcase
                end
                case(state)
                    IDLE: begin
                        owns_session<=0; scrub_to_fault<=0;
                        if(abort_pending) begin
                            abort_job<=1; scrub_index<=0; state<=SCRUB;
                            error_scrub<=0; scrub_to_result<=0;
                        end else if(dispatch_valid && dispatch_ready) begin
                            descriptor<=dispatch_descriptor; descriptor_addr<=dispatch_desc_addr;
                            ctx_id<=dispatch_descriptor[4:3];
                            dma_job<=dispatch_dma; legacy<=0; raw_job<=0;
                            first_fragment<=dispatch_descriptor[7];
                            last_fragment<=dispatch_descriptor[8];
                            result_code_reg<=0; result_tag_reg<=0;
                            result_bytes_reg<=0; retained_count<=0;
                            match_status<=0; fail_status<=0; protocol_status<=0;
                            state<=VALIDATE;
                        end else if(cmd_valid && cmd_ready) begin
                            descriptor<=legacy_descriptor; descriptor_addr<=0;
                            ctx_id<=0; dma_job<=0; legacy<=1; raw_job<=0;
                            first_fragment<=1; last_fragment<=1;
                            result_code_reg<=0; result_tag_reg<=0;
                            result_bytes_reg<=0; retained_count<=0;
                            match_status<=0; fail_status<=0; protocol_status<=0;
                            state<=VALIDATE;
                        end else if(in_valid && in_ready) begin
                            selected_slot<=0; aes_block<=in_block;
                            direction<=in_enc_dec; raw_tag<=in_tag_id;
                            raw_job<=1; legacy<=0; dma_job<=0;
                            match_status<=0; fail_status<=0; protocol_status<=0;
                            state<=LOAD_KEY;
                        end
                    end
                    VALIDATE: begin
                        status_allowed<=dma_job && status_range_safe;
                        if(validation_code!=0) begin
                            result_code_reg<=validation_code;
                            result_tag_reg<=0;
                            result_bytes_reg<=d_first ? 32'd0 : context_read[714:683];
                            descriptor<=0;
                            if(legacy) begin protocol_status<=1; state<=TAG; end
                            else state<=RESULT;
                        end else begin
                            owns_session<=1;
                            if(d_first) begin
                                work<=0;
                                work[0]<=1; work[2:1]<=d_mode; work[3]<=d_decrypt;
                                work[4]<=dma_job; work[6:5]<=d_slot; work[103:8]<=d_iv;
                                work[615:488]<={d_iv,d_mode==2 ? 32'd2 : 32'd1};
                                live_mask[ctx_id]<=1; bindings[ctx_id]<=d_slot;
                            end else work<=context_read;
                            selected_slot<=d_slot; direction<=d_decrypt; output_mode<=d_mode;
                            aad_total<=d_aad; payload_total<=d_payload;
                            aad_remaining<=d_aad; payload_remaining<=d_payload;
                            aad_addr<=d_aad_addr; src_addr<=d_src; dst_addr<=d_dst;
                            expected_latched<=d_tag; descriptor<=0;
                            beat_left<=0; ecb_count<=0; ecb_block<=0;
                            state<=LOAD_KEY;
                        end
                    end
                    LOAD_KEY: if(aes_key_ready) state<=KEY_WAIT;
                    KEY_WAIT: if(aes_loaded && !aes_busy) begin
                        if(raw_job) state<=RAW_START;
                        else if(first_fragment && mode==2) state<=H_START;
                        else state<=NEXT;
                    end
                    RAW_START: if(aes_in_ready) state<=RAW_WAIT;
                    RAW_WAIT: if(aes_out_valid) begin
                        aes_block<=aes_out_block; state<=RAW_OUT;
                    end
                    RAW_OUT: if(out_ready) begin
                        aes_block<=0; raw_tag<=0; raw_job<=0; direction<=0;
                        state<=IDLE;
                    end
                    H_START: if(aes_in_ready) state<=H_WAIT;
                    H_WAIT: if(aes_out_valid) begin work[359:232]<=aes_out_block; state<=MASK_START; end
                    MASK_START: if(aes_in_ready) state<=MASK_WAIT;
                    MASK_WAIT: if(aes_out_valid) begin work[487:360]<=aes_out_block; state<=NEXT; end
                    NEXT: begin
                        if(aad_remaining==0 && payload_remaining!=0 && mode==2 && !work[7]) begin
                            work[7]<=1;
                            if(pending_count!=0) begin
                                hash_block<=pending_hash; work[871:744]<=0;
                                work[876:872]<=0; gh_return<=NEXT; state<=GH_START;
                            end
                        end else if(aad_remaining!=0 || payload_remaining!=0) begin
                            if(aad_remaining==0 && mode!=0 && keystream_count==0)
                                state<=CTR_START;
                            else if(dma_job) state<=READ_REQ;
                            else if(beat_left==0) state<=GET_BEAT;
                            else begin
                                current_byte<=beat_hold[127:120]; beat_hold<=beat_hold<<8;
                                beat_left<=beat_left-1'b1; state<=BYTE;
                            end
                        end else if(!last_fragment) state<=SAVE;
                        else if(mode==2) begin
                            if(pending_count!=0) begin
                                hash_block<=pending_hash; work[871:744]<=0;
                                work[876:872]<=0; gh_return<=LENGTH; state<=GH_START;
                            end else state<=LENGTH;
                        end else state<=FINALIZE;
                    end
                    GET_BEAT: if(data_valid) begin
                        if(data_is_aad!=(aad_remaining!=0) || valid_bytes!=required_bytes) begin
                            result_code_reg<=6; result_tag_reg<=0;
                            result_bytes_reg<=data_bits[34:3];
                            protocol_status<=1; scrub_index<=0; error_scrub<=1;
                            scrub_to_result<=1; state<=SCRUB;
                        end else begin
                            beat_hold<=data_in; beat_left<=valid_bytes; state<=NEXT;
                        end
                    end
                    READ_REQ: if(io_ready) state<=READ_RSP;
                    READ_RSP: if(io_rsp_valid) begin
                        if(io_error) begin
                            result_code_reg<=8; result_tag_reg<=0;
                            result_bytes_reg<=data_bits[34:3];
                            scrub_index<=0; error_scrub<=1; scrub_to_result<=1; state<=SCRUB;
                        end else begin current_byte<=io_rbyte; state<=BYTE; end
                    end
                    BYTE: begin
                        current_byte<=0;
                        if(aad_remaining!=0) begin
                            aad_remaining<=aad_remaining-1'b1;
                            work[679:616]<=aad_bits+64'd8;
                            if(pending_count==15) begin
                                hash_block<=appended_hash; work[871:744]<=0;
                                work[876:872]<=0; gh_return<=NEXT; state<=GH_START;
                            end else begin
                                work[871:744]<=appended_hash;
                                work[876:872]<=pending_count+1'b1; state<=NEXT;
                            end
                        end else begin
                            payload_remaining<=payload_remaining-1'b1;
                            work[743:680]<=data_bits+64'd8;
                            work[1022:1010]<=stored_count+1'b1;
                            destination_store[ctx_id*CAP+stored_count]<=
                                dma_job ? dst_addr+(payload_total-payload_remaining) : 32'd0;
                            if(mode==0) begin
                                if(ecb_count==15) begin
                                    aes_block<=appended_ecb; ecb_block<=0; ecb_count<=0; state<=ECB_START;
                                end else begin
                                    ecb_block<=appended_ecb; ecb_count<=ecb_count+1'b1; state<=NEXT;
                                end
                            end else begin
                                payload_store[ctx_id*CAP+stored_count]<=transformed_byte;
                                work[1004:877]<=keystream<<8;
                                work[1009:1005]<=keystream_count-1'b1;
                                if(mode==2) begin
                                    if(pending_count==15) begin
                                        hash_block<=appended_hash; work[871:744]<=0;
                                        work[876:872]<=0; gh_return<=NEXT; state<=GH_START;
                                    end else begin
                                        work[871:744]<=appended_hash;
                                        work[876:872]<=pending_count+1'b1; state<=NEXT;
                                    end
                                end else state<=NEXT;
                            end
                        end
                    end
                    CTR_START: if(aes_in_ready) begin
                        work[615:488]<={counter[127:32],counter[31:0]+32'd1};
                        if(counter[31:0]==32'hffffffff) work[1023]<=1;
                        state<=CTR_WAIT;
                    end
                    CTR_WAIT: if(aes_out_valid) begin
                        work[1004:877]<=aes_out_block; work[1009:1005]<=16; state<=NEXT;
                    end
                    ECB_START: if(aes_in_ready) state<=ECB_WAIT;
                    ECB_WAIT: if(aes_out_valid) begin
                        for(i=0;i<16;i=i+1)
                            payload_store[ctx_id*CAP+stored_count-16+i]<=aes_out_block[127-8*i-:8];
                        aes_block<=0; state<=NEXT;
                    end
                    GH_START: if(!gh_busy) state<=GH_WAIT;
                    GH_WAIT: if(gh_done) begin
                        work[231:104]<=gh_result; hash_block<=0; state<=gh_return;
                    end
                    LENGTH: begin
                        hash_block<={aad_bits,data_bits}; gh_return<=FINALIZE; state<=GH_START;
                    end
                    FINALIZE: begin
                        result_bytes_reg<=data_bits[34:3];
                        retained_count<=stored_count; drain_index<=0;
                        if(mode==2) result_tag_reg<=tag_mask^accumulator;
                        else result_tag_reg<=0;
                        expected_latched<=0;
                        if(mode==2 && decrypt && (tag_mask^accumulator)!=expected_latched) begin
                            result_code_reg<=7; fail_status<=1;
                            if(!legacy) result_tag_reg<=0;
                            scrub_index<=0; error_scrub<=1; scrub_to_result<=1; state<=SCRUB;
                        end else begin
                            result_code_reg<=0; match_status<=mode==2 && decrypt;
                            if(dma_job) begin
                                if(stored_count!=0) state<=WRITE_REQ;
                                else begin
                                    scrub_index<=0; error_scrub<=0; scrub_to_result<=1; state<=SCRUB;
                                end
                            end else begin
                                work<=0;
                                beat_hold<=0; beat_left<=0; current_byte<=0;
                                aes_block<=0; hash_block<=0; ecb_block<=0;
                                if(legacy) state<=TAG;
                                else state<=RESULT;
                            end
                        end
                    end
                    SAVE: begin
                        result_code_reg<=0; result_tag_reg<=0;
                        result_bytes_reg<=data_bits[34:3];
                        work<=0; beat_hold<=0; beat_left<=0; current_byte<=0;
                        aes_block<=0; hash_block<=0; ecb_block<=0;
                        expected_latched<=0;
                        state<=RESULT;
                    end
                    RESULT: if(result_ready) state<=WAIT_RETIRE;
                    WAIT_RETIRE: if(scheduler_fault) begin
                        result_code_reg<=8; result_tag_reg<=0;
                        if(owns_session) begin
                            scrub_index<=0; error_scrub<=1;
                            scrub_to_fault<=1; state<=SCRUB;
                        end else state<=FAULT_ACK;
                    end else if(scheduler_retire) begin
                        result_tag_reg<=0;
                        if(result_code_reg==0 && last_fragment && !dma_job && retained_count!=0)
                            state<=DRAIN;
                        else if(result_code_reg==0 && last_fragment && !dma_job) begin
                            scrub_index<=0; error_scrub<=0; scrub_to_result<=0; state<=SCRUB;
                        end else begin
                            state<=IDLE; result_code_reg<=0; result_bytes_reg<=0;
                            dma_job<=0; legacy<=0;
                        end
                    end
                    TAG: if(tag_ready) begin
                        result_tag_reg<=0;
                        if(result_code_reg==0 && retained_count!=0) state<=DRAIN;
                        else if(result_code_reg==0) begin
                            scrub_index<=0; error_scrub<=0; scrub_to_result<=0; state<=SCRUB;
                        end
                        else begin
                            result_code_reg<=0; legacy<=0; state<=IDLE;
                        end
                    end
                    DRAIN: if(out_ready) begin
                        for(i=0;i<16;i=i+1)
                            if(i<drain_bytes && drain_index+i<CAP) begin
                                payload_store[ctx_id*CAP+drain_index+i]<=0;
                                destination_store[ctx_id*CAP+drain_index+i]<=0;
                            end
                        if(drain_index+drain_bytes==retained_count) begin
                            scrub_index<=0; error_scrub<=0; scrub_to_result<=0; state<=SCRUB;
                        end else drain_index<=drain_index+drain_bytes;
                    end
                    WRITE_REQ: if(io_ready) state<=WRITE_RSP;
                    WRITE_RSP: if(io_rsp_valid) begin
                        if(io_error) begin
                            result_code_reg<=8; result_tag_reg<=0;
                            scrub_index<=0; error_scrub<=1; scrub_to_result<=1; state<=SCRUB;
                        end else begin
                            payload_store[ctx_id*CAP+drain_index]<=0;
                            destination_store[ctx_id*CAP+drain_index]<=0;
                            if(drain_index+1'b1==retained_count) begin
                                scrub_index<=0; error_scrub<=0; scrub_to_result<=1; state<=SCRUB;
                            end else begin drain_index<=drain_index+1'b1; state<=WRITE_REQ; end
                        end
                    end
                    SCRUB: begin
                        payload_store[(abort_job ? abort_id : ctx_id)*CAP+scrub_index]<=0;
                        destination_store[(abort_job ? abort_id : ctx_id)*CAP+scrub_index]<=0;
                        work<=0; beat_hold<=0; beat_left<=0; current_byte<=0;
                        ecb_block<=0; ecb_count<=0; aes_block<=0; hash_block<=0;
                        expected_latched<=0; aad_remaining<=0; payload_remaining<=0;
                        if(scrub_index==CAP-1) begin scrub_index<=0; state<=CLEAR; end
                        else scrub_index<=scrub_index+1'b1;
                    end
                    CLEAR: begin
                        live_mask[context_clear_id]<=0; bindings[context_clear_id]<=0;
                        if(abort_job) begin
                            abort_job<=0; abort_pending<=0; csr_pending<=1;
                            csr_data<=0; csr_bad<=0; state<=IDLE;
                        end else if(scrub_to_fault) begin
                            retained_count<=0; scrub_to_fault<=0; state<=FAULT_ACK;
                        end else if(scrub_to_result) begin
                            if(error_scrub) retained_count<=0;
                            if(legacy) state<=TAG; else state<=RESULT;
                        end else begin
                            retained_count<=0; drain_index<=0; result_bytes_reg<=0;
                            direction<=0; output_mode<=0; legacy<=0; dma_job<=0;
                            state<=IDLE;
                        end
                    end
                    FAULT_ACK: state<=WAIT_RETIRE;
                    default: begin
                        result_code_reg<=6; result_tag_reg<=0;
                        scrub_index<=0; error_scrub<=1; scrub_to_result<=1; state<=SCRUB;
                    end
                endcase
            end
        end
    end
endmodule
