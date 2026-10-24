`timescale 1ns / 1ps
module tb_firing_uart;
    reg clk=0,clk_in=0,resetn=0,uart_rx=1;
    always #5 clk=~clk;
    always #10 clk_in=~clk_in;
    wire uart_tx,sclk,sdio,cs_n,trigger,init_done,init_busy,dac_reset,clken;
    wire [7:0] rsp_cmd,rsp_status;
    wire rsp_valid,tx_done;
    reg chip_sdo=0;
    reg [15:0] read_word=0;
    reg read_mode=0;
    integer read_transactions=0;
`ifdef FIRING_FAST
    localparam real BIT_NS=160.0;
    wire [7:0] rx_data,rsp_seq;
    wire rx_valid,rx_error,cfg_valid,cfg_ready,cfg_last,cfg_done,rsp_ready;
    wire [14:0] cfg_addr; wire [15:0] cfg_wdata,cfg_rdata,rsp_data;
    uart_cmd_rx #(.SYS_CLK_HZ(100000000),.BAUD_RATE(6250000)) rx_i
        (.clk(clk),.resetn(resetn),.uart_rx(uart_rx),.data(rx_data),.data_valid(rx_valid),.frame_error(rx_error));
    ad9106_cmd_parser #(.SYS_CLK_HZ(100000000)) parser_i
        (.clk(clk),.resetn(resetn),.rx_data(rx_data),.rx_valid(rx_valid),.rx_error(rx_error),.init_done(init_done),
         .cfg_valid(cfg_valid),.cfg_ready(cfg_ready),.cfg_addr(cfg_addr),.cfg_wdata(cfg_wdata),.cfg_last(cfg_last),
         .cfg_done(cfg_done),.cfg_rdata(cfg_rdata),.rsp_data(rsp_data),.rsp_valid(rsp_valid),.rsp_ready(rsp_ready),.rsp_seq(rsp_seq),.rsp_cmd(rsp_cmd),
         .rsp_status(rsp_status),.rsp_done(tx_done),.busy());
    uart_cmd_tx #(.SYS_CLK_HZ(100000000),.BAUD_RATE(6250000)) tx_i
        (.clk(clk),.resetn(resetn),.rsp_valid(rsp_valid),.rsp_ready(rsp_ready),.rsp_seq(rsp_seq),.rsp_cmd(rsp_cmd),
         .rsp_status(rsp_status),.rsp_data(rsp_data),.uart_tx(uart_tx),.busy(),.done(tx_done));
    AD9106 #(.SYS_CLK_HZ(100000000),.SPI_CLK_HZ(50000000),.RESET_LOW_CYCLES(2),
        .RESET_HIGH_CYCLES(2),.RUNTIME_UPDATE_CYCLES(4)) dac_i
        (.clk(clk),.resetn(resetn),.ad9106_sdo(chip_sdo),.ad9106_sclk(sclk),.ad9106_sdio(sdio),
         .ad9106_cs_n(cs_n),.ad9106_reset(dac_reset),.ad9106_trigger(trigger),.ad9106_clken(clken),
         .init_done(init_done),.init_busy(init_busy),.cfg_valid(cfg_valid),.cfg_ready(cfg_ready),
         .cfg_addr(cfg_addr),.cfg_wdata(cfg_wdata),.cfg_last(cfg_last),.cfg_done(cfg_done),.cfg_rdata(cfg_rdata));
`else
    localparam real BIT_NS=1000000000.0/115200.0;
    design_1_wrapper dut(.clk_in(clk_in),.resetn(resetn),.uart_rx_0(uart_rx),.uart_tx_0(uart_tx),
        .ad9106_sdo_0(chip_sdo),.ad9106_sclk_0(sclk),.ad9106_sdio_0(sdio),.ad9106_cs_n_0(cs_n),
        .ad9106_reset_0(dac_reset),.ad9106_trigger_0(trigger),.ad9106_clken_0(clken),
        .init_done_0(init_done),.init_busy_0(init_busy));
    assign rsp_cmd=dut.design_1_i.ad9106_cmd_parser_0_rsp_cmd;
    assign rsp_status=dut.design_1_i.ad9106_cmd_parser_0_rsp_status;
    assign rsp_valid=dut.design_1_i.ad9106_cmd_parser_0_rsp_valid;
    assign tx_done=dut.design_1_i.uart_cmd_tx_0_done;
`endif
    reg [7:0] frames[0:131071],request[0:23],reply[0:16383],decoded;
    reg [31:0] expected_spi[0:8191],shift=0;
    reg [15:0] chip_reg[0:127]; reg [11:0] chip_sram[0:4095];
    integer counts_fd,result_fd,spi_fd,num_frames,num_spi,pattern_cycles,read_count;
    integer bits=0,writes=0,oracle_index=0,replies=0,reply_read=0,i,j,k,base;
    reg verify_program=0,committed=0,verify_retrigger=0;
    integer retrigger_spi_index=0;
    integer scene_triggers=0,scene_stops=0;
    reg [31:0] last_spi_write=0,previous_spi_write=0;
    integer checked_starts=0;
    // Independent rule from Rev.C p31 / ADI support, not the PC-generated oracle.
    always @(negedge trigger) if(resetn) begin
        if(previous_spi_write !== 32'h001e0001 || last_spi_write !== 32'h001d0001)
            $fatal(1,"Trigger before RUN then RAMUPDATE: %h %h",previous_spi_write,last_spi_write);
        checked_starts=checked_starts+1;
    end
    always @(negedge trigger) if(resetn && (verify_program || committed))
        scene_triggers=scene_triggers+1;
    always @(negedge cs_n) begin bits=0; shift=0; end
    always @(posedge sclk) if(!cs_n) begin shift={shift[30:0],sdio}; bits=bits+1; end
    always @(negedge sclk) if(!cs_n) begin
        if(bits==16) begin read_mode=shift[15]; read_word=chip_reg[shift[6:0]]; end
        if(bits>=16 && bits<32 && read_mode) chip_sdo=read_word[31-bits];
        else chip_sdo=0;
    end
    always @(posedge cs_n) if(resetn && bits!=0) begin
        if(bits!=32) $fatal(1,"Malformed firing SPI frame");
        if(shift[31]) begin read_transactions=read_transactions+1; end else begin
        if(verify_program && oracle_index<num_spi) begin
            if(shift !== expected_spi[oracle_index])
                $fatal(1,"Program SPI[%0d] expected %h got %h",oracle_index,expected_spi[oracle_index],shift);
            $fdisplay(spi_fd,"%0.3f,%04h,%04h",$realtime,shift[30:16],shift[15:0]);
            oracle_index=oracle_index+1;
        end else if(verify_retrigger && retrigger_spi_index<2) begin
            case(retrigger_spi_index)
                0: if(shift !== 32'h001e0001) $fatal(1,"Retrigger must only set RUN");
                1: if(shift !== 32'h001d0001) $fatal(1,"Retrigger must apply RAMUPDATE last");
            endcase
            retrigger_spi_index=retrigger_spi_index+1;
        end
        if(shift[30:16]>='h6000 && shift[30:16]<='h6fff) begin
            if(chip_reg['h1e] !== 4) $fatal(1,"SRAM written outside MEM_ACCESS mode");
            chip_sram[shift[30:16]-'h6000]=shift[15:4];
        end else if(shift[30:16]<128) chip_reg[shift[30:16]]=shift[15:0];
        writes=writes+1;
        previous_spi_write=last_spi_write;
        last_spi_write=shift;
        end
    end
    always @(posedge clk) if(resetn && rsp_valid && rsp_status==0) begin
        if(rsp_cmd=='h40 || rsp_cmd=='h41) begin
            if(trigger !== 1 || cs_n !== 1) $fatal(1,"Upload ACK before stopped/write-complete state");
        end else if(rsp_cmd=='h42) begin
            if(trigger !== 0 || cs_n !== 1) $fatal(1,"Final ACK before restart/abort completed");
        end else if(rsp_cmd=='h43) begin
            if(trigger !== 1 || cs_n !== 1) $fatal(1,"Abort ACK before trigger stopped");
        end
    end
    initial forever begin
        @(negedge uart_tx); #(BIT_NS/2);
        if(uart_tx !== 0) $fatal(1,"Firing UART start bit");
        for(j=0;j<8;j=j+1) begin #(BIT_NS); decoded[j]=uart_tx; end
        #(BIT_NS); if(uart_tx !== 1) $fatal(1,"Firing UART stop bit");
        reply[replies]=decoded; replies=replies+1;
    end
    task new_request(input [7:0] seq,input [7:0] cmd);
        begin
            for(integer n=0;n<24;n=n+1) request[n]=0;
            request[0]='haa; request[1]='h55; request[2]=seq; request[3]=cmd; request[23]=13;
        end
    endtask
    task checksum;
        begin
            request[22]=0;
            for(integer n=2;n<22;n=n+1) request[22]=request[22]^request[n];
        end
    endtask
    task send_request;
        begin
            for(integer n=0;n<24;n=n+1) begin
                uart_rx=0; #(BIT_NS);
                for(integer b=0;b<8;b=b+1) begin uart_rx=request[n][b]; #(BIT_NS); end
                uart_rx=1; #(BIT_NS);
            end
        end
    endtask
    task expect_reply(input [7:0] status);
        begin
            wait(replies>=reply_read+8);
            if(reply[reply_read] !== 'h55 || reply[reply_read+1] !== 'haa ||
               reply[reply_read+2] !== request[2] || reply[reply_read+3] !== request[3] ||
               reply[reply_read+4] !== status || reply[reply_read+5] !== (request[2]^request[3]^status) ||
               reply[reply_read+6] !== 13 || reply[reply_read+7] !== 10)
                $fatal(1,"Firing ACK seq=%0d cmd=%h expected status=%0d actual=%0d",request[2],request[3],status,reply[reply_read+4]);
            reply_read=reply_read+8; wait(tx_done); #(BIT_NS);
        end
    endtask
    task read_request(input [15:0] address,input [15:0] value,input [7:0] status);
        begin
            new_request(230,'h45); request[4]=address[15:8];request[5]=address[7:0];checksum;
            send_request;wait(replies>=reply_read+10);
            if(reply[reply_read]!=='h55 || reply[reply_read+1]!=='haa ||
               reply[reply_read+2]!==230 || reply[reply_read+3]!=='h45 ||
               reply[reply_read+4]!==status || reply[reply_read+5]!==value[15:8] ||
               reply[reply_read+6]!==value[7:0] ||
               reply[reply_read+7]!==(8'd230 ^ 8'h45 ^ status ^ value[15:8] ^ value[7:0]) ||
               reply[reply_read+8]!==13 || reply[reply_read+9]!==10)
                $fatal(1,"Read reply mismatch address=%h",address);
            reply_read=reply_read+10; wait(tx_done); #(BIT_NS);
        end
    endtask
    task block_request(input [7:0] seq,input [15:0] addr,input [7:0] count,input [15:0] d0,input [15:0] d1);
        begin
            new_request(seq,'h41); request[4]=addr[15:8]; request[5]=addr[7:0]; request[6]=count;
            request[7]=d0[15:8]; request[8]=d0[7:0]; request[9]=d1[15:8]; request[10]=d1[7:0]; checksum;
        end
    endtask
    initial begin #(64'd5000000000); $fatal(1,"Firing simulation timeout"); end
    initial begin
        counts_fd=$fopen("../firing_scene_fixture/counts.txt","r");
        if(!counts_fd) $fatal(1,"Missing PC-generated firing fixture");
        read_count=$fscanf(counts_fd,"%d %d %d",num_frames,num_spi,pattern_cycles); $fclose(counts_fd);
        if(read_count!=3 || num_frames>5400 || num_spi>8192 || pattern_cycles<1)
            $fatal(1,"Invalid fixture size or pattern duration");
        $readmemh("../firing_scene_fixture/frames.mem",frames,0,num_frames*24-1);
        $readmemh("../firing_scene_fixture/expected_spi.mem",expected_spi,0,num_spi-1);
        spi_fd=$fopen("firing_spi.csv","w"); $fdisplay(spi_fd,"time_ns,address_hex,data_hex");
        #1000; resetn=1; wait(init_done); #(BIT_NS);
        if(chip_reg['h1f] !== 1 || chip_reg['h2a] !== 'h0101 || chip_reg['h2b] !== 'h0101)
            $fatal(1,"Power-on configuration is not finite two-pattern mode");
        base=writes;
        block_request(200,'h6000,1,'h1230,0); send_request; expect_reply(8);
        new_request(201,'h40); request[4]=1; checksum; send_request; expect_reply(4);
        if(writes!=base) $fatal(1,"Rejected opening command wrote SPI");
        verify_program=1;
        for(i=0;i<num_frames;i=i+1) begin
            for(k=0;k<24;k=k+1) request[k]=frames[i*24+k];
            send_request; expect_reply(0);
        end
        verify_program=0;
        committed=1;
        // Observe longer than the reported 25 ms burst: no automatic SPI or retrigger.
        #30000000;
        if(oracle_index!=num_spi || trigger !== 0 || init_busy !== 0 || scene_triggers!=1)
            $fatal(1,"First scene trigger/count mismatch");
        if(chip_reg['h1e] !== 1 || writes!=base+num_spi)
            $fatal(1,"Unexpected RUN clear or automatic SPI after COMMIT");
        // Save the ACTUALLY transmitted SRAM and channel registers for independent analysis.
        result_fd=$fopen("observed_sram.mem","w");
        for(i=0;i<4096;i=i+1) $fdisplay(result_fd,"%03h",chip_sram[i]);
        $fclose(result_fd);
        result_fd=$fopen("observed_registers.mem","w");
        for(i=0;i<128;i=i+1) $fdisplay(result_fd,"%04h",chip_reg[i]);
        $fclose(result_fd);
        $display("PASS FIRING: %0d PC frames -> %0d exact SPI writes, four channels committed synchronously",num_frames,num_spi);

        base=writes;
        if(chip_reg['h1f] !== 1 || chip_reg['h2a] !== 'h0101 || chip_reg['h2b] !== 'h0101)
            $fatal(1,"Finite two-pattern playback was not programmed");
        chip_reg['h10]=16'ha55a;
        read_request('h1f,1,0);
        read_request('h2a,'h0101,0);
        read_request('h10,16'ha55a,0);
        chip_reg['h10]=16'hffff;
        read_request('h10,16'hffff,0);
        read_request('h61,0,4);
        if(writes!=base || scene_triggers!=1 || read_transactions!=4)
            $fatal(1,"Readback changed configuration or trigger");
        $display("PASS READBACK: 0001/0101/A55A/FFFF, UART checksum, invalid address, no trigger/write");
        verify_retrigger=1;
        new_request(224,'h44); checksum; send_request; expect_reply(0);
        #30000000;
        if(writes!=base+2 || retrigger_spi_index!=2 || trigger !== 0 || chip_reg['h1f] !== 1 ||
           chip_reg['h1e] !== 1 || scene_triggers!=2)
            $fatal(1,"Retrigger changed SRAM, cleared RUN, or emitted extra trigger");
        verify_retrigger=0;
        $display("PASS CHIP FINITE: 30 ms after each trigger, no automatic writes, RUN stays 1");
        base=writes;
        new_request(202,1); checksum; send_request; expect_reply(8);
        block_request(203,'h6000,1,0,0); send_request; expect_reply(8);
        new_request(204,'h42); checksum; send_request; expect_reply(8);
        if(writes!=base) $fatal(1,"Closed-session or legacy command wrote SPI");
        // The PC Stop button may mute an already running, committed scene.
        new_request(222,'h43); checksum; send_request; expect_reply(0);
        if(writes!=base+13 || trigger !== 1)
            $fatal(1,"Post-commit abort did not mute the scene");
        base=writes;
        new_request(225,'h44); checksum; send_request; expect_reply(8);
        if(writes!=base) $fatal(1,"Retrigger after abort wrote SPI");
        new_request(205,'h40); checksum; send_request; expect_reply(0);
        base=writes;
        new_request(206,'h40); checksum; send_request; expect_reply(8);
        block_request(207,'h6000,1,0,0); send_request; expect_reply(8);
        block_request(208,'h001d,1,1,0); send_request; expect_reply(4);
        block_request(209,'h001e,1,1,0); send_request; expect_reply(4);
        block_request(210,'h6fff,2,0,0); send_request; expect_reply(4);
        block_request(211,'h6000,8,0,0); send_request; expect_reply(4);
        if(writes!=base) $fatal(1,"Invalid block partially wrote SPI");
        block_request(212,'h001e,1,4,0); send_request; expect_reply(0);
        base=writes;
        new_request(213,'h42); checksum; send_request; expect_reply(8);
        block_request(214,'h6000,1,'h1230,0); request[22]=request[22]^1; send_request; expect_reply(2);
        if(writes!=base) $fatal(1,"Failed commit/checksum wrote SPI");
        new_request(215,'h43); checksum; send_request; expect_reply(0);
        if(writes!=base+13 || trigger !== 1) $fatal(1,"Abort failed");
        for(i='h22;i<='h25;i=i+1) if(chip_reg[i] !== 0) $fatal(1,"Abort did not clear offset");
        for(i='h2e;i<='h35;i=i+1) if(chip_reg[i] !== 0) $fatal(1,"Abort did not mute constant/gain");
        $fclose(spi_fd);
        if(checked_starts!=3) $fatal(1,"Expected boot, commit, retrigger startup checks");
        $display("PASS START ORDER: boot, COMMIT and RETRIGGER use RUN -> RAMUPDATE -> TRIGGER");
        $display("PASS FIRING SUMMARY: upload, sequence wrap, all channel data, ACK timing, block validation, legacy isolation and abort mute");
        $finish;
    end
endmodule
