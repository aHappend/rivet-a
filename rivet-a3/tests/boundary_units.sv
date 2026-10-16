`timescale 1ns/1ps
module boundary_units;
    reg clk=0;
    always #5 clk=~clk;
    reg rst_n;
    reg write_en=0,clear_en=0;
    reg [1:0] write_id=0,clear_id=0,read_id=0;
    reg [1279:0] write_data=0;
    wire [1279:0] context_read;
    rivet_a3_context_store context_store(.clk(clk),.rst_n(rst_n),
        .write_en(write_en),.write_id(write_id),.write_data(write_data),
        .read_id(read_id),.read_data(context_read),.clear_en(clear_en),.clear_id(clear_id));
    reg d_first=0;
    reg [1:0] d_mode=2;
    reg [31:0] d_aad=0,d_payload=0;
    // This is an exact retained excerpt of the delivered top's combinational
    // boundary arithmetic, driven solely through a real context-store interface.
    `include "arithmetic.svh"
    reg load_valid=0,key_len_sel=0,lock_in=0,result_ready=0;
    reg [1:0] slot_id=0,read_slot_id=0;
    reg [255:0] key_in=0;
    reg [3:0] bound_mask=0;
    wire load_ready,result_valid,read_key_len;
    wire [3:0] result_code,valid_mask,lock_mask;
    wire [255:0] read_key;
    rivet_a3_key_table key_table(.*);
    integer checked=0,i,j;
    reg [1279:0] expected_records[0:3];
    reg [64:0] independent_aad,independent_data;
    reg [32:0] independent_blocks,independent_available;
    reg [63:0] old_aad,old_data;
    reg [31:0] old_counter;
    integer stream;
    task tick;begin @(posedge clk);#1;@(negedge clk);#1;end endtask
    task store_record(input [1279:0] value);
        reg [1279:0] previous;
        begin
            #1;
            previous=context_read;
            write_data=value;write_id=read_id;write_en=1;#1;
            if(context_read!==previous) $fatal(1,"context write visible before edge");
            tick;write_en=0;#1;
            if(context_read!==value) $fatal(1,"context record did not edge-commit");
            checked=checked+1;
        end
    endtask
    task check_math;
        begin
            old_aad=d_first?0:context_read[679:616];
            old_data=d_first?0:context_read[743:680];
            old_counter=d_first?(d_mode==2?2:1):context_read[519:488];
            stream=d_first?0:context_read[1009:1005];
            independent_aad={1'b0,old_aad}+{30'b0,d_aad,3'b0};
            independent_data={1'b0,old_data}+{30'b0,d_payload,3'b0};
            independent_blocks=0;
            if(d_payload>stream) independent_blocks=(d_payload-stream)/16+
                                                    (((d_payload-stream)%16)!=0);
            independent_available=33'h100000000-{1'b0,old_counter};
            if(!d_first && context_read[1023]) independent_available=0;
            #1;
            if(new_aad_bits!==independent_aad || new_data_bits!==independent_data ||
               counter_blocks!==independent_blocks || counters_available!==independent_available)
                $fatal(1,"actual top boundary arithmetic mismatch");
            checked=checked+1;
        end
    endtask
    task key_load(input integer slot,length_i,lock_i,code_i,input [255:0] value);
        begin
            slot_id=slot;key_len_sel=length_i;lock_in=lock_i;key_in=value;load_valid=1;
            #1;while(!load_ready) tick;
            tick;load_valid=0;repeat(3) tick;
            if(result_valid!==1 || result_code!==code_i || load_ready!==0)
                $fatal(1,"key result/semantic readiness");
            result_ready=1;tick;result_ready=0;checked=checked+1;
        end
    endtask
    always @(posedge clk or negedge clk) begin
        if(!rst_n && {context_read,load_ready,result_valid,result_code,read_key,
                     read_key_len,valid_mask,lock_mask}!==0) $fatal(1,"unit reset leakage");
    end
    initial begin
        rst_n=0;#0;
        if(context_read!==0 || read_key!==0 || load_ready!==0)
            $fatal(1,"time-zero unit reset");
        #1;
        if(context_read!==0 || read_key!==0) $fatal(1,"time-zero unit reset");
        repeat(2) tick;rst_n=1;tick;
        for(i=0;i<4;i=i+1) begin
            read_id=i;write_id=i;
            expected_records[i]={40{32'h01020304}} ^ i;
            store_record(expected_records[i]);
        end
        for(i=0;i<4;i=i+1) begin
            read_id=i;#1;
            if(context_read!==expected_records[i]) $fatal(1,"four-bank isolation");
            checked=checked+1;
        end
        clear_en=1;clear_id=2;write_en=1;write_id=1;write_data=0;tick;
        clear_en=0;write_en=0;
        read_id=2;#1;if(context_read!==0) $fatal(1,"clear priority");
        read_id=1;#1;if(context_read!==expected_records[1]) $fatal(1,"clear must suppress write");
        checked=checked+2;
        read_id=0;
        // Crossing 2^64 bit counters and the final legal inc32 counter, without
        // pretending to have transmitted exabytes or forcing top-level state.
        for(i=0;i<8;i=i+1) begin
            write_data=0;write_data[679:616]=64'hfffffffffffffff0+i;
            write_data[743:680]=64'hfffffffffffffff8+i;
            write_data[615:488]={96'hcafe,32'hffffffff};
            write_data[1009:1005]=i*2;write_data[1023]=i&1;
            store_record(write_data);
            for(j=0;j<5;j=j+1) begin
                d_first=0;d_aad=j;d_payload=(j==4)?32'hffffffff:j*16;check_math;
                d_first=1;d_mode=j%3;check_math;
            end
        end
        key_load(0,0,0,0,256'h00112233445566778899aabbccddeeff_ffffffffffffffffffffffffffffffff);
        read_slot_id=0;#1;
        if(read_key!==256'h00112233445566778899aabbccddeeff_00000000000000000000000000000000 ||
           read_key_len!==0) $fatal(1,"AES128 unused key half not zero");
        bound_mask=1;key_load(0,1,0,3,256'h1234);
        if(read_key!==256'h00112233445566778899aabbccddeeff_00000000000000000000000000000000)
            $fatal(1,"bound rejection mutated key");
        bound_mask=0;key_load(1,1,1,0,256'h1234);key_load(1,0,0,3,0);
        read_slot_id=1;#1;if(read_key!==256'h1234 || read_key_len!==1 || lock_mask!==2)
            $fatal(1,"locked rejection mutated key");
        write_en=1;clear_en=1;load_valid=1;rst_n=0;#1;
        repeat(2) tick;write_en=0;clear_en=0;load_valid=0;rst_n=1;tick;
        for(i=0;i<4;i=i+1) begin
            read_id=i;read_slot_id=i;#1;
            if(context_read!==0 || read_key!==0 || valid_mask!==0 || lock_mask!==0)
                $fatal(1,"reset did not dominate key/context mutation");
            checked=checked+1;
        end
        $display("UNIT_RESULT comparisons=%0d arithmetic_cases=80 context_banks=4",checked);
        $finish;
    end
endmodule
