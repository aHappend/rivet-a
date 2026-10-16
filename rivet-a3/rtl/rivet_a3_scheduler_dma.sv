module rivet_a3_scheduler_dma (
    input wire clk, rst_n, enable,
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
    output wire dispatch_valid,
    input wire dispatch_ready,
    output wire [511:0] dispatch_descriptor,
    output wire dispatch_dma,
    output wire [7:0] dispatch_cookie,
    output wire [31:0] dispatch_desc_addr,
    input wire result_valid,
    output wire result_ready,
    input wire [3:0] result_code,
    input wire [1:0] result_ctx_id,
    input wire result_final,
    input wire [127:0] result_tag,
    input wire [31:0] result_bytes,
    input wire result_status_allowed,
    input wire io_valid,
    output wire io_ready,
    input wire io_write,
    input wire [31:0] io_addr,
    input wire [7:0] io_wbyte,
    output wire io_rsp_valid,
    input wire io_rsp_ready,
    output wire [7:0] io_rbyte,
    output wire io_error,
    output wire queued, active,
    output wire fault_valid,
    input wire fault_ready,
    output reg retire,
    output reg [3:0] event_code
);
    localparam IDLE=0, FETCH_REQ=1, FETCH_RSP=2, DISPATCH=3, WORK=4,
               IO_REQ=5, IO_RSP=6, IO_RETURN=7, STATUS_REQ=8,
               STATUS_RSP=9, COMPLETE=10, FAULT=11;
    reg [3:0] state;
    reg awake, origin, status_known;
    reg [31:0] high_addr[0:1], normal_addr[0:1];
    reg [7:0] high_cookie[0:1], normal_cookie[0:1];
    reg high_head, high_tail, normal_head, normal_tail;
    reg [1:0] high_count, normal_count;
    reg [31:0] desc_addr, status_addr;
    reg [511:0] descriptor;
    reg [1:0] fetch_index;
    reg status_index;
    reg [7:0] cookie;
    reg [3:0] code;
    reg [1:0] ctx;
    reg final_flag;
    reg [127:0] tag;
    reg [31:0] byte_count;
    reg byte_write, byte_error;
    reg [31:0] byte_addr;
    reg [7:0] byte_data, byte_read;
    integer i;
    wire select_high = state==IDLE && enable && high_count!=0;
    wire select_normal = state==IDLE && enable && high_count==0 && normal_count!=0;
    wire enqueue = dma_submit_valid && dma_submit_ready;
    wire direct_select = state==IDLE && enable && high_count==0 && normal_count==0;
    wire visible = rst_n && awake;
    wire [127:0] status_lo = {40'd0,7'd0,final_flag,6'd0,ctx,cookie,
                               byte_count,28'd0,code};
    function automatic [127:0] reverse_bytes(input [127:0] value);
        integer b;
        begin
            for (b=0;b<16;b=b+1)
                reverse_bytes[8*b+:8]=value[127-8*b-:8];
        end
    endfunction
    assign queued = visible && (high_count!=0 || normal_count!=0);
    assign active = visible && state!=IDLE;
    assign fault_valid = visible && state==FAULT;
    assign dma_submit_ready = visible &&
        (dma_priority ? high_count<2 : normal_count<2);
    assign task_ready = visible && direct_select && dispatch_ready;
    assign dispatch_valid = visible && (state==DISPATCH || (direct_select && task_valid));
    assign dispatch_descriptor = dispatch_valid ?
        (state==DISPATCH ? descriptor : task_descriptor) : 512'd0;
    assign dispatch_dma = dispatch_valid && state==DISPATCH;
    assign dispatch_cookie = dispatch_valid ?
        (state==DISPATCH ? cookie : task_descriptor[448+:8]) : 8'd0;
    assign dispatch_desc_addr = dispatch_dma ? desc_addr : 32'd0;
    assign result_ready = visible && state==WORK;
    assign completion_valid = visible && state==COMPLETE;
    assign completion_cookie = completion_valid ? cookie : 8'd0;
    assign completion_ctx_id = completion_valid ? ctx : 2'd0;
    assign completion_code = completion_valid ? code : 4'd0;
    assign completion_final = completion_valid && final_flag;
    assign completion_tag = completion_valid ? tag : 128'd0;
    assign io_ready = visible && state==WORK && origin && !result_valid;
    assign io_rsp_valid = visible && state==IO_RETURN;
    assign io_rbyte = io_rsp_valid ? byte_read : 8'd0;
    assign io_error = io_rsp_valid && byte_error;
    assign mem_req_valid = visible &&
        (state==FETCH_REQ || state==IO_REQ || state==STATUS_REQ);
    assign mem_req_write = mem_req_valid &&
        (state==STATUS_REQ || (state==IO_REQ && byte_write));
    assign mem_req_addr = !mem_req_valid ? 32'd0 :
        state==FETCH_REQ ? desc_addr+{26'd0,fetch_index,4'd0} :
        state==STATUS_REQ ? status_addr+{27'd0,status_index,4'd0} :
        {byte_addr[31:4],4'd0};
    assign mem_req_wdata = !mem_req_write ? 128'd0 :
        state==STATUS_REQ ? (status_index ? reverse_bytes(tag) : status_lo) :
        ({120'd0,byte_data} << (8*byte_addr[3:0]));
    assign mem_req_wstrb = !mem_req_write ? 16'd0 :
        state==STATUS_REQ ? 16'hffff : (16'h0001 << byte_addr[3:0]);
    assign mem_rsp_ready = visible &&
        (state==FETCH_RSP || state==IO_RSP || state==STATUS_RSP);
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            awake<=0; state<=IDLE; origin<=0; status_known<=0;
            high_head<=0; high_tail<=0; normal_head<=0; normal_tail<=0;
            high_count<=0; normal_count<=0;
            desc_addr<=0; status_addr<=0; descriptor<=0; fetch_index<=0;
            status_index<=0; cookie<=0; code<=0; ctx<=0; final_flag<=0;
            tag<=0; byte_count<=0; byte_write<=0; byte_error<=0;
            byte_addr<=0; byte_data<=0; byte_read<=0; retire<=0; event_code<=0;
            for(i=0;i<2;i=i+1) begin
                high_addr[i]<=0; normal_addr[i]<=0;
                high_cookie[i]<=0; normal_cookie[i]<=0;
            end
        end else begin
            awake<=1;
            retire<=0;
            event_code<=0;
            if (awake) begin
                case ({enqueue && dma_priority, select_high})
                    2'b10: high_count<=high_count+1'b1;
                    2'b01: high_count<=high_count-1'b1;
                    default: begin end
                endcase
                case ({enqueue && !dma_priority, select_normal})
                    2'b10: normal_count<=normal_count+1'b1;
                    2'b01: normal_count<=normal_count-1'b1;
                    default: begin end
                endcase
                if(enqueue) begin
                    if(dma_priority) begin
                        high_addr[high_tail]<=dma_desc_addr;
                        high_cookie[high_tail]<=dma_cookie;
                        high_tail<=!high_tail;
                    end else begin
                        normal_addr[normal_tail]<=dma_desc_addr;
                        normal_cookie[normal_tail]<=dma_cookie;
                        normal_tail<=!normal_tail;
                    end
                end
                case(state)
                    IDLE: begin
                        if(select_high || select_normal) begin
                            if(select_high) begin
                                desc_addr<=high_addr[high_head];
                                cookie<=high_cookie[high_head];
                                high_addr[high_head]<=0; high_cookie[high_head]<=0;
                                high_head<=!high_head;
                                if(high_addr[high_head][3:0]!=0 ||
                                   high_addr[high_head]>32'hffffffc0) begin
                                    code<=1; event_code<=1; state<=COMPLETE;
                                end else state<=FETCH_REQ;
                            end else begin
                                desc_addr<=normal_addr[normal_head];
                                cookie<=normal_cookie[normal_head];
                                normal_addr[normal_head]<=0; normal_cookie[normal_head]<=0;
                                normal_head<=!normal_head;
                                if(normal_addr[normal_head][3:0]!=0 ||
                                   normal_addr[normal_head]>32'hffffffc0) begin
                                    code<=1; event_code<=1; state<=COMPLETE;
                                end else state<=FETCH_REQ;
                            end
                            origin<=1; descriptor<=0; fetch_index<=0;
                            status_known<=0; ctx<=0; final_flag<=0; tag<=0; byte_count<=0;
                        end else if(task_valid && task_ready) begin
                            cookie<=task_descriptor[448+:8]; origin<=0;
                            status_known<=0; descriptor<=0;
                            state<=WORK;
                        end
                    end
                    FETCH_REQ: if(mem_req_ready) state<=FETCH_RSP;
                    FETCH_RSP: if(mem_rsp_valid) begin
                        if(mem_rsp_error) begin
                            code<=8; tag<=0; event_code<=8; state<=COMPLETE;
                            descriptor<=0;
                        end else begin
                            descriptor[128*fetch_index+:128]<=mem_rsp_rdata;
                            if(fetch_index==3) state<=DISPATCH;
                            else begin fetch_index<=fetch_index+1'b1; state<=FETCH_REQ; end
                        end
                    end
                    DISPATCH: if(dispatch_ready) begin
                        status_addr<=descriptor[128+:32];
                        status_known<=descriptor[131:128]==0 &&
                                      descriptor[128+:32]<=32'hffffffe0;
                        descriptor<=0;
                        state<=WORK;
                    end
                    WORK: begin
                        if(result_valid) begin
                            code<=result_code; ctx<=result_ctx_id;
                            final_flag<=result_final; tag<=result_tag;
                            byte_count<=result_bytes; status_index<=0;
                            if(origin && status_known && result_status_allowed) state<=STATUS_REQ;
                            else state<=COMPLETE;
                        end else if(io_valid && io_ready) begin
                            byte_write<=io_write; byte_addr<=io_addr;
                            byte_data<=io_wbyte; byte_read<=0; byte_error<=0;
                            state<=IO_REQ;
                        end
                    end
                    IO_REQ: if(mem_req_ready) state<=IO_RSP;
                    IO_RSP: if(mem_rsp_valid) begin
                        byte_error<=mem_rsp_error;
                        byte_read<=mem_rsp_error ? 8'd0 :
                            mem_rsp_rdata[8*byte_addr[3:0]+:8];
                        state<=IO_RETURN;
                    end
                    IO_RETURN: if(io_rsp_ready) begin
                        byte_write<=0; byte_addr<=0; byte_data<=0;
                        byte_read<=0; byte_error<=0; state<=WORK;
                    end
                    STATUS_REQ: if(mem_req_ready) state<=STATUS_RSP;
                    STATUS_RSP: if(mem_rsp_valid) begin
                        if(mem_rsp_error) begin
                            code<=8; tag<=0; event_code<=8; state<=FAULT;
                        end else if(status_index) state<=COMPLETE;
                        else begin status_index<=1; state<=STATUS_REQ; end
                    end
                    FAULT: if(fault_ready) state<=COMPLETE;
                    COMPLETE: if(completion_ready) begin
                        retire<=1; state<=IDLE; origin<=0;
                        cookie<=0; ctx<=0; code<=0; final_flag<=0;
                        tag<=0; byte_count<=0; status_addr<=0; desc_addr<=0;
                        status_known<=0; fetch_index<=0; status_index<=0;
                    end
                    default: begin state<=IDLE; event_code<=8; end
                endcase
            end
        end
    end
endmodule
