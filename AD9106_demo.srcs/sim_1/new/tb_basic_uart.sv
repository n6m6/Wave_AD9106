`timescale 1ns/1ps
module tb_basic_uart;
    reg clk=0,clk_in=0,resetn=0,uart_rx=1;
    always #5 clk=~clk;
    always #10 clk_in=~clk_in;
    wire uart_tx,sclk,sdio,cs_n,trigger,initialized;
`ifdef FIRING_FAST
    localparam real BIT_NS=160;
    wire [7:0] rx_data,rsp_seq,rsp_cmd,rsp_status;
    wire rx_valid,rx_error,cfg_valid,cfg_ready,cfg_last,cfg_done,rsp_valid,rsp_ready,tx_done;
    wire [14:0] cfg_addr; wire [15:0] cfg_wdata,cfg_rdata,rsp_data;
    uart_cmd_rx #(.BAUD_RATE(6250000)) rx_i(.clk(clk),.resetn(resetn),.uart_rx(uart_rx),.data(rx_data),.data_valid(rx_valid),.frame_error(rx_error));
    ad9106_cmd_parser parser_i(.clk(clk),.resetn(resetn),.rx_data(rx_data),.rx_valid(rx_valid),.rx_error(rx_error),.init_done(initialized),
        .cfg_valid(cfg_valid),.cfg_ready(cfg_ready),.cfg_addr(cfg_addr),.cfg_wdata(cfg_wdata),.cfg_last(cfg_last),.cfg_done(cfg_done),.cfg_rdata(cfg_rdata),
        .rsp_data(rsp_data),.rsp_valid(rsp_valid),.rsp_ready(rsp_ready),.rsp_seq(rsp_seq),.rsp_cmd(rsp_cmd),.rsp_status(rsp_status),.rsp_done(tx_done),.busy());
    uart_cmd_tx #(.BAUD_RATE(6250000)) tx_i(.clk(clk),.resetn(resetn),.rsp_valid(rsp_valid),.rsp_ready(rsp_ready),.rsp_seq(rsp_seq),
        .rsp_cmd(rsp_cmd),.rsp_status(rsp_status),.rsp_data(rsp_data),.uart_tx(uart_tx),.busy(),.done(tx_done));
    AD9106 #(.RESET_LOW_CYCLES(2),.RESET_HIGH_CYCLES(2)) dac_i(.clk(clk),.resetn(resetn),.ad9106_sdo(1'b0),
        .ad9106_sclk(sclk),.ad9106_sdio(sdio),.ad9106_cs_n(cs_n),.ad9106_trigger(trigger),.init_done(initialized),
        .cfg_valid(cfg_valid),.cfg_ready(cfg_ready),.cfg_addr(cfg_addr),.cfg_wdata(cfg_wdata),.cfg_last(cfg_last),.cfg_done(cfg_done),.cfg_rdata(cfg_rdata));
`else
    localparam real BIT_NS=1000000000.0/115200;
    design_1_wrapper dut(.clk_in(clk_in),.resetn(resetn),.uart_rx_0(uart_rx),.uart_tx_0(uart_tx),.ad9106_sdo_0(1'b0),
        .ad9106_sclk_0(sclk),.ad9106_sdio_0(sdio),.ad9106_cs_n_0(cs_n),.ad9106_trigger_0(trigger),.init_done_0(initialized));
`endif
    reg [7:0] frames[0:131071],packet[0:23],replies[0:16383],rxbyte;
    reg [31:0] oracle[0:8191],shift=0;
    reg [15:0] regs[0:127];
    integer num_frames,num_spi,duration,fd,i,j,k,bits=0,reply_count=0,read_index=0,oracle_index=0;
    integer events=0,staged=0,writes=0,triggers=0,saved_writes;
    reg verify_setup=0,monitor=0,check_values=1;
    realtime update_time[0:31];
    always @(negedge uart_tx) begin
        #(BIT_NS*1.5);
        for(integer b=0;b<8;b=b+1) begin rxbyte[b]=uart_tx; #(BIT_NS); end
        if(uart_tx!==1) $fatal(1,"Bad TX stop bit");
        replies[reply_count]=rxbyte; reply_count=reply_count+1;
    end
    always @(negedge trigger) if(monitor) triggers=triggers+1;
    always @(negedge cs_n) begin bits=0; shift=0; end
    always @(posedge sclk) if(!cs_n) begin shift={shift[30:0],sdio}; bits=bits+1; end
    always @(posedge cs_n) if(resetn && bits>0) begin
        if(bits!=32 || shift[31]) $fatal(1,"Malformed/unexpected SPI read");
        if(shift[30:16]>=128 && shift[30:16]<'h6000) $fatal(1,"FPGA virtual address leaked onto SPI");
        if(shift[30:16]<128) regs[shift[30:16]]=shift[15:0];
        writes=writes+1;
        if(verify_setup) begin
            if(shift!==oracle[oracle_index]) $fatal(1,"Basic setup mismatch index %d got %h expected %h",oracle_index,shift,oracle[oracle_index]);
            oracle_index=oracle_index+1;
            if(oracle_index==num_spi) begin verify_setup=0; monitor=1; end
        end else if(monitor) begin
            if(shift[30:16]>='h2e && shift[30:16]<='h35) staged=staged+1;
            if(shift[30:16]=='h1d) begin
                if(staged==8) begin
                    update_time[events]=$realtime;
                    if(check_values) begin
                        if(events<4 && regs['h31] !== ((events%2==0)?16'h3330:16'h0000)) $fatal(1,"Square high/low sequence wrong");
                        if(events<4 && (regs['h34]!==16'h0cd0 || regs['h32]!==16'h1330)) $fatal(1,"DDS gains wrong");
                        if(events==4 && (regs['h32]!==0 || regs['h33]!==0 || regs['h34]!==0 || regs['h35]!==0 || regs['h31]!==0)) $fatal(1,"Final event did not mute outputs");
                    end
                    $display("BASIC UPDATE %0d at %0.3f ns DAC1=%h gain2=%h",events,$realtime,regs['h31],regs['h34]);
                    events=events+1;
                end
                staged=0;
            end
        end
    end
    task send_packet;
        begin
            for(integer p=0;p<24;p=p+1) begin
                uart_rx=0; #(BIT_NS);
                for(integer b=0;b<8;b=b+1) begin uart_rx=packet[p][b]; #(BIT_NS); end
                uart_rx=1; #(BIT_NS);
            end
            wait(reply_count>=read_index+8);
            if(replies[read_index]!==8'h55 || replies[read_index+1]!==8'haa || replies[read_index+3]!==packet[3] || replies[read_index+4]!==0)
                $fatal(1,"Basic UART ACK failure cmd=%h status=%h",packet[3],replies[read_index+4]);
            read_index=read_index+8; #(BIT_NS);
        end
    endtask
    task command(input [7:0] cmd);
        begin
            for(integer p=0;p<24;p=p+1) packet[p]=0;
            packet[0]='haa;packet[1]='h55;packet[2]=220;packet[3]=cmd;packet[22]=220^cmd;packet[23]=13;
            send_packet;
        end
    endtask
    task verify_burst;
        begin
            #4000000;
            if(events!=5 || triggers!=1 || trigger!==1 || regs['h1e]!==1) $fatal(1,"Wrong basic burst count/trigger/RUN events=%d triggers=%d",events,triggers);
            for(integer e=1;e<5;e=e+1)
                if(update_time[e]-update_time[e-1]<499950 || update_time[e]-update_time[e-1]>500050) $fatal(1,"Square edge timing not 500 us");
            saved_writes=writes; #1000000;
            if(writes!=saved_writes) $fatal(1,"Extra writes after final mute");
        end
    endtask
    initial begin #(64'd3000000000); $fatal(1,"Basic UART timeout"); end
    initial begin
        fd=$fopen("../firing_scene_fixture/counts.txt","r");
        i=$fscanf(fd,"%d %d %d",num_frames,num_spi,duration); $fclose(fd);
        $readmemh("../firing_scene_fixture/frames.mem",frames,0,num_frames*24-1);
        $readmemh("../firing_scene_fixture/expected_spi.mem",oracle,0,num_spi-1);
        #100;resetn=1;wait(initialized); #10000;verify_setup=1;
        for(i=0;i<num_frames;i=i+1) begin
            for(j=0;j<24;j=j+1) packet[j]=frames[i*24+j];
            send_packet;
        end
        verify_burst;
        if(regs['h26]!==16'h3201 || regs['h27]!==16'h3201 || regs['h3e]!==0 || regs['h3f]!==16'h7100 || regs['h53]!==1 || regs['h40]!==16'h4000)
            $fatal(1,"DDS routing/frequency/phase/cycles wrong");
        $display("PASS BASIC: UART configuration, square 1 kHz/two cycles, DDS registers, synchronized updates, final zero");
        events=0;triggers=0;command('h44);verify_burst;
        $display("PASS BASIC RETRIGGER: restores gains after final zero and emits exactly two square cycles");
        events=0;triggers=0;check_values=0;command('h44);
        command('h43);#4000000;
        if(regs['h32]!==0 || regs['h33]!==0 || regs['h34]!==0 || regs['h35]!==0 || trigger!==1) $fatal(1,"Abort did not mute");
        saved_writes=writes;#2000000;if(writes!=saved_writes) $fatal(1,"Player continued after abort");
        $display("PASS FIRING SUMMARY: basic modes upload, two cycles, retrigger, abort and no RUN clear");
        $finish;
    end
endmodule
