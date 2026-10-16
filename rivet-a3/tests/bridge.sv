`timescale 1ns/1ps
module bridge;
    parameter integer CAPACITY=1;
    reg clk=0;
    always #5 clk=~clk;
    reg rst_n;
    reg key_valid=0, key_len_sel=0, in_valid=0, in_enc_dec=0, out_ready=0;
    reg [255:0] key_in=0;
    reg [127:0] in_block=0;
    reg [7:0] in_tag_id=0;
    reg cmd_valid=0, cmd_decrypt=0, data_valid=0, data_is_aad=0, tag_ready=0;
    reg [95:0] iv_in=0;
    reg [31:0] aad_bytes=0, payload_bytes=0;
    reg [127:0] expected_tag=0, data_in=0;
    reg [4:0] valid_bytes=0;
    reg [1:0] key_slot_id=0;
    reg key_lock=0, key_result_ready=0, task_valid=0;
    reg [511:0] task_descriptor=0;
    reg dma_submit_valid=0, dma_priority=0, completion_ready=0;
    reg [31:0] dma_desc_addr=0;
    reg [7:0] dma_cookie=0;
    reg mem_req_ready=0, mem_rsp_valid=0, mem_rsp_error=0;
    reg [127:0] mem_rsp_rdata=0;
    reg csr_valid=0, csr_write=0, csr_rsp_ready=0;
    reg [7:0] csr_addr=0;
    reg [31:0] csr_wdata=0;
    wire key_ready,key_loaded,in_ready,out_valid,out_enc_dec,busy,err_unloaded_key;
    wire cmd_ready,data_ready,out_is_gcm,tag_valid,tag_match,auth_fail,protocol_error;
    wire key_result_valid,task_ready,dma_submit_ready,completion_valid,completion_final;
    wire mem_req_valid,mem_req_write,mem_rsp_ready,csr_ready,csr_rsp_valid,csr_error;
    wire [127:0] out_block,tag_out,completion_tag,mem_req_wdata;
    wire [7:0] out_tag_id,completion_cookie;
    wire [4:0] out_valid_bytes;
    wire [3:0] key_result_code,completion_code;
    wire [1:0] completion_ctx_id;
    wire [31:0] mem_req_addr,csr_rdata;
    wire [15:0] mem_req_wstrb;
    rivet_a3_top #(.MAX_PAYLOAD_BLOCKS(CAPACITY)) dut(.*);

    // Expectations are populated before stimulus, never from DUT internals.
    reg [127:0] expected_output[0:32767], expected_completion_tag[0:4095];
    integer expected_size[0:32767], expected_direction[0:32767];
    integer expected_gcm[0:32767], expected_id[0:32767], output_gate[0:32767];
    integer expected_cookie[0:4095], expected_ctx[0:4095];
    integer expected_code[0:4095], expected_final[0:4095];
    reg [127:0] expected_legacy_tag[0:4095];
    integer expected_match[0:4095], expected_fail[0:4095], expected_protocol[0:4095];
    integer outputs_added=0,outputs_seen=0,completions_added=0,completions_seen=0;
    integer tags_added=0,tags_seen=0,key_results_seen=0,csr_seen=0;
    reg [7:0] memory[0:131071], write_value[0:131071];
    integer write_left[0:131071];
    reg readable[0:131071];
    integer fetch_expected[0:4095],fetch_added=0,fetch_seen=0;
    integer cycles=0, comparisons=0, requests=0,responses=0;
    integer output_stalls=0,completion_stalls=0,request_stalls=0;
    integer tag_stalls=0,key_stalls=0,csr_stalls=0,reset_checks=0;
    integer reads=0,writes=0,handshakes=0, simultaneous=0;
    integer fault_address=-1,fault_write=-1,fault_skip=0,faults_seen=0;
    integer pending=0,delay_left=0,response_error=0,hold_response=0;
    reg [127:0] response_data=0;
    reg random_ready=1;
    reg release_check=0;
    reg [31:0] rng=1;
    integer k,n,address;
    task check_known;
        begin
            if ((^{key_ready,key_loaded,in_ready,out_valid,out_block,out_tag_id,
                out_enc_dec,busy,err_unloaded_key,cmd_ready,data_ready,out_valid_bytes,
                out_is_gcm,tag_valid,tag_out,tag_match,auth_fail,protocol_error,
                key_result_valid,key_result_code,task_ready,dma_submit_ready,
                completion_valid,completion_cookie,completion_ctx_id,completion_code,
                completion_final,completion_tag,mem_req_valid,mem_req_write,
                mem_req_addr,mem_req_wdata,mem_req_wstrb,mem_rsp_ready,csr_ready,
                csr_rsp_valid,csr_rdata,csr_error}) === 1'bx)
                $fatal(1,"XZ public output at cycle %0d",cycles);
            if (!rst_n || release_check) begin
                if ({key_ready,key_loaded,in_ready,out_valid,out_block,out_tag_id,
                    out_enc_dec,busy,err_unloaded_key,cmd_ready,data_ready,out_valid_bytes,
                    out_is_gcm,tag_valid,tag_out,tag_match,auth_fail,protocol_error,
                    key_result_valid,key_result_code,task_ready,dma_submit_ready,
                    completion_valid,completion_cookie,completion_ctx_id,completion_code,
                    completion_final,completion_tag,mem_req_valid,mem_req_write,
                    mem_req_addr,mem_req_wdata,mem_req_wstrb,mem_rsp_ready,csr_ready,
                    csr_rsp_valid,csr_rdata,csr_error} !== 0)
                    $fatal(1,"RESET/release-before-first-edge nonzero public output");
                reset_checks=reset_checks+1;
            end
        end
    endtask
    reg output_held=0,completion_held=0,request_held=0,tag_held=0,key_held=0,csr_held=0;
    reg [151:0] output_previous;
    reg [142:0] completion_previous;
    reg [176:0] request_previous;
    reg [130:0] tag_previous;
    reg [3:0] key_previous;
    reg [32:0] csr_previous;
    integer canceled_outputs=0,canceled_requests=0,reset_epochs=0;
    integer output_bytes=0,write_lanes=0,auth_rejections=0;
    reg [6:0] input_held=0;
    reg [259:0] input_key_previous;
    reg [136:0] input_raw_previous;
    reg [288:0] input_command_previous;
    reg [133:0] input_data_previous;
    reg [511:0] input_task_previous;
    reg [40:0] input_dma_previous,input_csr_previous;
    always @(posedge clk) begin
        check_known;
        cycles=cycles+1;
        if(rst_n) begin
            if(input_held[0] && (!key_valid ||
                {key_in,key_len_sel,key_slot_id,key_lock}!==input_key_previous))
                $fatal(1,"invalid key stimulus: changed under backpressure");
            if(input_held[1] && (!in_valid ||
                {in_block,in_enc_dec,in_tag_id}!==input_raw_previous))
                $fatal(1,"invalid raw stimulus: changed under backpressure");
            if(input_held[2] && (!cmd_valid ||
                {iv_in,aad_bytes,payload_bytes,expected_tag,cmd_decrypt}!==input_command_previous))
                $fatal(1,"invalid command stimulus: changed under backpressure");
            if(input_held[3] && (!data_valid ||
                {data_in,valid_bytes,data_is_aad}!==input_data_previous))
                $fatal(1,"invalid stream stimulus: changed under backpressure");
            if(input_held[4] && (!task_valid || task_descriptor!==input_task_previous))
                $fatal(1,"invalid descriptor stimulus: changed under backpressure");
            if(input_held[5] && (!dma_submit_valid ||
                {dma_desc_addr,dma_priority,dma_cookie}!==input_dma_previous))
                $fatal(1,"invalid DMA stimulus: changed under backpressure");
            if(input_held[6] && (!csr_valid ||
                {csr_write,csr_addr,csr_wdata}!==input_csr_previous))
                $fatal(1,"invalid CSR stimulus: changed under backpressure");
            input_held={csr_valid&&!csr_ready,dma_submit_valid&&!dma_submit_ready,
                        task_valid&&!task_ready,data_valid&&!data_ready,
                        cmd_valid&&!cmd_ready,in_valid&&!in_ready,key_valid&&!key_ready};
            input_key_previous={key_in,key_len_sel,key_slot_id,key_lock};
            input_raw_previous={in_block,in_enc_dec,in_tag_id};
            input_command_previous={iv_in,aad_bytes,payload_bytes,expected_tag,cmd_decrypt};
            input_data_previous={data_in,valid_bytes,data_is_aad};
            input_task_previous=task_descriptor;
            input_dma_previous={dma_desc_addr,dma_priority,dma_cookie};
            input_csr_previous={csr_write,csr_addr,csr_wdata};
            if(output_held && (!out_valid ||
                {out_block,out_tag_id,out_enc_dec,out_valid_bytes,out_is_gcm} !== output_previous))
                $fatal(1,"output changed during stall");
            if(completion_held && (!completion_valid ||
                {completion_cookie,completion_ctx_id,completion_code,completion_final,completion_tag}
                !== completion_previous)) $fatal(1,"completion changed during stall");
            if(request_held && (!mem_req_valid ||
                {mem_req_write,mem_req_addr,mem_req_wdata,mem_req_wstrb} !== request_previous))
                $fatal(1,"request changed during stall");
            if(tag_held && (!tag_valid ||
                {tag_out,tag_match,auth_fail,protocol_error} !== tag_previous))
                $fatal(1,"tag changed during stall");
            if(key_held && (!key_result_valid || key_result_code !== key_previous))
                $fatal(1,"key result changed during stall");
            if(csr_held && (!csr_rsp_valid || {csr_rdata,csr_error} !== csr_previous))
                $fatal(1,"CSR result changed during stall");
            output_held=out_valid&&!out_ready;
            completion_held=completion_valid&&!completion_ready;
            request_held=mem_req_valid&&!mem_req_ready;
            tag_held=tag_valid&&!tag_ready;
            key_held=key_result_valid&&!key_result_ready;
            csr_held=csr_rsp_valid&&!csr_rsp_ready;
            output_previous={out_block,out_tag_id,out_enc_dec,out_valid_bytes,out_is_gcm};
            completion_previous={completion_cookie,completion_ctx_id,completion_code,
                                 completion_final,completion_tag};
            request_previous={mem_req_write,mem_req_addr,mem_req_wdata,mem_req_wstrb};
            tag_previous={tag_out,tag_match,auth_fail,protocol_error};
            key_previous=key_result_code; csr_previous={csr_rdata,csr_error};
            if(output_held) output_stalls=output_stalls+1;
            if(completion_held) completion_stalls=completion_stalls+1;
            if(request_held) request_stalls=request_stalls+1;
            if(tag_held) tag_stalls=tag_stalls+1;
            if(key_held) key_stalls=key_stalls+1;
            if(csr_held) csr_stalls=csr_stalls+1;
            if(out_valid) begin
                if(outputs_seen>=outputs_added) $fatal(1,"unexpected output");
                if(output_gate[outputs_seen]>completions_seen+tags_seen)
                    $fatal(1,"payload released before completion/tag retirement");
                if(out_block !== expected_output[outputs_seen] ||
                   out_valid_bytes !== expected_size[outputs_seen] ||
                   out_enc_dec !== (expected_direction[outputs_seen]!=0) ||
                   out_is_gcm !== (expected_gcm[outputs_seen]!=0) ||
                   out_tag_id !== expected_id[outputs_seen])
                    $fatal(1,"OUTPUT mismatch index=%0d actual=%h expected=%h bytes=%0d",
                           outputs_seen,out_block,expected_output[outputs_seen],out_valid_bytes);
                comparisons=comparisons+1;
                if(out_ready) begin
                    outputs_seen=outputs_seen+1;output_bytes=output_bytes+out_valid_bytes;
                end
            end
            if(completion_valid) begin
                if(pending || mem_rsp_valid)
                    $fatal(1,"completion before final memory response retirement");
                if(completions_seen>=completions_added) $fatal(1,"unexpected completion");
                if(completion_cookie !== expected_cookie[completions_seen] ||
                   completion_ctx_id !== expected_ctx[completions_seen] ||
                   completion_code !== expected_code[completions_seen] ||
                   completion_final !== (expected_final[completions_seen]!=0) ||
                   completion_tag !== expected_completion_tag[completions_seen])
                    $fatal(1,"COMPLETION mismatch index=%0d code=%0d expected=%0d tag=%h expected_tag=%h",
                        completions_seen,completion_code,expected_code[completions_seen],
                        completion_tag,expected_completion_tag[completions_seen]);
                comparisons=comparisons+1;
                if(completion_ready) begin
                    completions_seen=completions_seen+1;
                    if(completion_code==7) auth_rejections=auth_rejections+1;
                end
            end
            if(tag_valid) begin
                if(tags_seen>=tags_added) $fatal(1,"unexpected legacy tag");
                if(tag_out !== expected_legacy_tag[tags_seen] ||
                   tag_match !== (expected_match[tags_seen]!=0) ||
                   auth_fail !== (expected_fail[tags_seen]!=0) ||
                   protocol_error !== (expected_protocol[tags_seen]!=0))
                    $fatal(1,"legacy tag mismatch index=%0d actual=%h expected=%h",
                           tags_seen,tag_out,expected_legacy_tag[tags_seen]);
                comparisons=comparisons+1;
                if(tag_ready) tags_seen=tags_seen+1;
            end
            if((out_valid || completion_valid || tag_valid || key_result_valid) && busy!==1)
                $fatal(1,"busy lost an unretired public reservation");
            if((out_valid || completion_valid || tag_valid) &&
               (key_ready || task_ready || cmd_ready || in_ready || data_ready))
                $fatal(1,"streaming engine offered a competing acceptance while reserved");
            if(key_result_valid && key_result_ready) key_results_seen=key_results_seen+1;
            if(csr_rsp_valid && csr_rsp_ready) csr_seen=csr_seen+1;
            if(mem_req_valid && mem_req_ready) begin
                if(pending || mem_rsp_valid) $fatal(1,"more than one outstanding memory request");
                if(mem_req_addr[3:0]!==0 || mem_req_addr>=131072)
                    $fatal(1,"invalid memory beat address %h",mem_req_addr);
                pending=1; requests=requests+1; response_data=0; response_error=0;
                delay_left=1+(rng%7);
                if(mem_req_addr==fault_address && (fault_write<0 || mem_req_write==fault_write)) begin
                    if(fault_skip==0) begin
                        response_error=1;fault_address=-1;faults_seen=faults_seen+1;
                    end else fault_skip=fault_skip-1;
                end
                if(!mem_req_write) begin
                    if(mem_req_wdata!==0 || mem_req_wstrb!==0)
                        $fatal(1,"nonzero read data/strobes");
                    if(!readable[mem_req_addr]) $fatal(1,"unexpected read %h",mem_req_addr);
                    if(fetch_seen<fetch_added && mem_req_addr==fetch_expected[fetch_seen])
                        fetch_seen=fetch_seen+1;
                    else begin
                        for(n=fetch_seen+1;n<fetch_added;n=n+1)
                            if(mem_req_addr==fetch_expected[n])
                                $fatal(1,"descriptor fetch priority/FIFO violation");
                    end
                    reads=reads+1;
                    for(n=0;n<16;n=n+1)
                        response_data[8*n+:8]=memory[mem_req_addr+n];
                end else begin
                    writes=writes+1;
                    response_data={rng,~rng,rng^32'hdeadbeef,32'hbad0da7a};
                    if(mem_req_wstrb===0) $fatal(1,"zero-strobe write");
                    for(n=0;n<16;n=n+1) if(mem_req_wstrb[n]) begin
                        address=mem_req_addr+n;
                        if(write_left[address]<=0 || mem_req_wdata[8*n+:8]!==write_value[address])
                            $fatal(1,"MEMORY WRITE mismatch address=%h data=%h expected=%h left=%0d",
                                   address,mem_req_wdata[8*n+:8],write_value[address],write_left[address]);
                        write_left[address]=write_left[address]-1;
                        write_lanes=write_lanes+1;
                        if(!response_error) memory[address]=mem_req_wdata[8*n+:8];
                        comparisons=comparisons+1;
                    end
                end
            end
            if(mem_rsp_valid && mem_rsp_ready) begin
                if(!pending) $fatal(1,"response without request");
                pending=0; responses=responses+1;
            end
        end else begin
            input_held=0;
            output_held=0;completion_held=0;request_held=0;tag_held=0;key_held=0;csr_held=0;
            if(pending) canceled_requests=canceled_requests+1;
            pending=0;
        end
    end
    always @(negedge clk) begin
        check_known;
        rng=(rng<<1) ^ (rng[31] ? 32'h04c11db7 : 0);
        if(!rst_n) begin
            mem_req_ready=0;mem_rsp_valid=0;mem_rsp_error=0;mem_rsp_rdata=0;
        end else begin
            mem_req_ready=(rng%5)!=0;
            if(mem_rsp_valid && !pending) begin
                mem_rsp_valid=0;mem_rsp_rdata=0;mem_rsp_error=0;
            end
            if(pending && !mem_rsp_valid && !hold_response) begin
                if(delay_left==0) begin
                    mem_rsp_valid=1;mem_rsp_rdata=response_data;mem_rsp_error=response_error;
                end else delay_left=delay_left-1;
            end
        end
        if(random_ready) begin
            out_ready=rst_n && (rng%4)!=0;
            completion_ready=rst_n && (rng%3)!=0;
            tag_ready=rst_n && (rng%5)!=0;
        end
    end
    task tick; begin @(posedge clk); #1; @(negedge clk); #1; end endtask
    task idle;
        begin
            while(busy) tick;
            repeat(3) tick;
        end
    endtask
    task expect_completion(input integer cookie_i,ctx_i,code_i,final_i,input [127:0] tag_i);
        begin
            expected_cookie[completions_added]=cookie_i;
            expected_ctx[completions_added]=ctx_i;
            expected_code[completions_added]=code_i;
            expected_final[completions_added]=final_i;
            expected_completion_tag[completions_added]=tag_i;
            completions_added=completions_added+1;
        end
    endtask
    task expect_output(input [127:0] value,input integer size_i,dir_i,gcm_i,id_i,gate_i);
        begin
            expected_output[outputs_added]=value;expected_size[outputs_added]=size_i;
            expected_direction[outputs_added]=dir_i;expected_gcm[outputs_added]=gcm_i;
            expected_id[outputs_added]=id_i;output_gate[outputs_added]=gate_i;
            outputs_added=outputs_added+1;
        end
    endtask
    task expect_tag(input [127:0] value,input integer match_i,fail_i,protocol_i);
        begin
            expected_legacy_tag[tags_added]=value;expected_match[tags_added]=match_i;
            expected_fail[tags_added]=fail_i;expected_protocol[tags_added]=protocol_i;
            tags_added=tags_added+1;
        end
    endtask
    task load_key(input integer slot_i,input [255:0] value,input integer length_i,lock_i,code_i);
        integer before_count;
        begin
            before_count=key_results_seen;
            key_slot_id=slot_i;key_in=value;key_len_sel=length_i;key_lock=lock_i;
            key_valid=1;key_result_ready=0;
            while(!key_ready) tick;
            tick;key_valid=0;
            while(!key_result_valid) tick;
            repeat(4) tick;
            if(key_result_code !== code_i) $fatal(1,"KEY result mismatch");
            comparisons=comparisons+1;
            key_result_ready=1;
            while(key_results_seen==before_count) tick;
            key_result_ready=0;tick;
        end
    endtask
    task submit(input [511:0] value);
        begin
            task_descriptor=value;task_valid=1;
            while(!task_ready) tick;
            tick;task_valid=0;
        end
    endtask
    task enqueue(input integer addr_i,priority_i,cookie_i);
        begin
            dma_desc_addr=addr_i;dma_priority=priority_i;dma_cookie=cookie_i;
            dma_submit_valid=1;
            #1;
            while(!dma_submit_ready) tick;
            tick;dma_submit_valid=0;
        end
    endtask
    task beat(input [127:0] value,input integer size_i,aad_i);
        begin
            data_in=value;valid_bytes=size_i;data_is_aad=aad_i;data_valid=1;
            while(!data_ready) tick;
            tick;data_valid=0;
            repeat(rng%4) tick;
        end
    endtask
    task raw(input [127:0] value,input integer dir_i,id_i);
        begin
            in_block=value;in_enc_dec=dir_i;in_tag_id=id_i;in_valid=1;
            while(!in_ready) tick;
            tick;in_valid=0;
        end
    endtask
    task command(input [95:0] iv_i,input integer aad_i,payload_i,dir_i,input [127:0] tag_i);
        begin
            iv_in=iv_i;aad_bytes=aad_i;payload_bytes=payload_i;cmd_decrypt=dir_i;
            expected_tag=tag_i;cmd_valid=1;
            while(!cmd_ready) tick;
            tick;cmd_valid=0;
        end
    endtask
    task csr(input integer address_i,write_i,value_i,expected_i,error_i);
        integer before_count;
        begin
            before_count=csr_seen;
            csr_addr=address_i;csr_write=write_i;csr_wdata=value_i;csr_valid=1;csr_rsp_ready=0;
            while(!csr_ready) tick;
            tick;csr_valid=0;
            while(!csr_rsp_valid) tick;
            repeat(4) tick;
            if(csr_rdata !== expected_i || csr_error !== (error_i!=0))
                $fatal(1,"CSR mismatch addr=%h actual=%h err=%b expected=%h err=%0d",
                       address_i,csr_rdata,csr_error,expected_i,error_i);
            comparisons=comparisons+1;csr_rsp_ready=1;
            while(csr_seen==before_count) tick;
            csr_rsp_ready=0;tick;
        end
    endtask
    task reset_device;
        begin
            reset_epochs=reset_epochs+1;
            rst_n=0;key_valid=0;in_valid=0;cmd_valid=0;data_valid=0;task_valid=0;
            dma_submit_valid=0;csr_valid=0;key_result_ready=0;csr_rsp_ready=0;
            #1;check_known;
            repeat(3) tick;
            rst_n=1;release_check=1;#1;check_known;release_check=0;
            tick;tick;
        end
    endtask
    task finish_case;
        begin
            idle;
            if(outputs_seen!=outputs_added || completions_seen!=completions_added ||
               tags_seen!=tags_added || fetch_seen!=fetch_added)
                $fatal(1,"missing output/completion/tag/fetch");
            if(pending || requests!=responses+canceled_requests) $fatal(1,"memory conservation");
            for(k=0;k<131072;k=k+1) begin
                if(write_left[k]!=0) $fatal(1,"missing write address=%h count=%0d",k,write_left[k]);
                readable[k]=0;
            end
        end
    endtask
    initial begin
        rst_n=0;
        for(k=0;k<131072;k=k+1) begin
            memory[k]=8'ha5;write_value[k]=0;write_left[k]=0;readable[k]=0;
        end
        #0;check_known;
        #1;check_known;
        reset_device;
        `include "scenarios.svh"
        finish_case;
        if(comparisons==0 || reset_checks==0) $fatal(1,"empty verification");
        $display("RESULT comparisons=%0d cycles=%0d outputs=%0d completions=%0d tags=%0d reads=%0d writes=%0d output_stalls=%0d completion_stalls=%0d request_stalls=%0d key_stalls=%0d csr_stalls=%0d tag_stalls=%0d faults=%0d reset_checks=%0d simultaneous=%0d canceled_outputs=%0d canceled_requests=%0d reset_epochs=%0d output_bytes=%0d write_lanes=%0d auth_rejections=%0d",
            comparisons,cycles,outputs_seen,completions_seen,tags_seen,reads,writes,
            output_stalls,completion_stalls,request_stalls,key_stalls,csr_stalls,tag_stalls,
            faults_seen,reset_checks,simultaneous,canceled_outputs,canceled_requests,reset_epochs,
            output_bytes,write_lanes,auth_rejections);
        $finish;
    end
endmodule
