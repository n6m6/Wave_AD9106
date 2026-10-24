`timescale 1ns / 1ps
// Actual generated top, MMCM simulation model and production parameters.
// No clock, SPI, reset-delay or UART parameter overrides are used.
module tb_top_uart;
    localparam real BIT_NS=1000000000.0/115200.0;
    reg clk_in=0, resetn=0, uart_rx=1;
    always #10 clk_in=~clk_in;
    wire uart_tx, sclk, sdio, cs_n, dac_reset, trigger, clken, init_done, init_busy;
    wire sys_clk, sys_resetn;
    design_1_wrapper dut (
        .clk_in(clk_in), .resetn(resetn), .uart_rx_0(uart_rx), .uart_tx_0(uart_tx),
        .ad9106_sdo_0(1'b0), .ad9106_sclk_0(sclk), .ad9106_sdio_0(sdio),
        .ad9106_cs_n_0(cs_n), .ad9106_reset_0(dac_reset), .ad9106_trigger_0(trigger),
        .ad9106_clken_0(clken), .init_done_0(init_done), .init_busy_0(init_busy));
    assign sys_clk=dut.design_1_i.clk_wiz_clk_out1;
    assign sys_resetn=dut.design_1_i.clk_wiz_locked;

    reg [7:0] request[0:23], reply[0:511];
    reg [14:0] wr_addr[0:32767];
    reg [15:0] wr_data[0:32767];
    reg [15:0] chip_reg[0:127];
    reg [11:0] chip_sram[0:4095], saved_arb[0:1484];
    reg [31:0] shift=0;
    reg [7:0] decoded;
    reg last_cfg_seen=0;
    integer bits=0, writes=0, replies=0, reply_read=0, init_checks=0;
    integer rx_events=0, tx_events=0, frame_errors=0;
    integer spi_fd, event_fd, wave_fd, i, j, base, point, code, spi_address;
    integer transaction_checks=0;
    realtime last_spi_edge=0, command_start=0, clock_start, elapsed_ms;

    initial begin
        spi_fd=$fopen("top_spi_writes.csv","w");
        event_fd=$fopen("top_events.csv","w");
        if(!spi_fd || !event_fd) $fatal(1,"Cannot create simulation evidence");
        $fdisplay(spi_fd,"time_ns,write_index,address_hex,data_hex");
        $fdisplay(event_fd,"time_ns,event,seq,cmd,status,spi_writes");
    end
    always @(negedge cs_n) begin bits=0; shift=0; last_spi_edge=0; end
    always @(posedge sclk) if(!cs_n) begin
        if(last_spi_edge != 0 && $realtime-last_spi_edge != 1000.0)
            $fatal(1,"SPI clock is not 1 MHz");
        last_spi_edge=$realtime;
        shift={shift[30:0],sdio}; bits=bits+1;
    end
    always @(negedge dac_reset) begin
        for(integer k=0;k<128;k=k+1) chip_reg[k]=0;
    end
    always @(posedge cs_n) if(resetn && sys_resetn && bits != 0) begin
        if(bits != 32 || shift[31]) $fatal(1,"Invalid physical SPI frame");
        spi_address=shift[30:16];
        wr_addr[writes]=spi_address; wr_data[writes]=shift[15:0];
        $fdisplay(spi_fd,"%0.3f,%0d,%04h,%04h",$realtime,writes,shift[30:16],shift[15:0]);
        if(spi_address >= 'h6000 && spi_address <= 'h6fff) begin
            if(chip_reg['h1e] !== 16'h0004 || shift[3:0] != 0)
                $fatal(1,"SRAM write without stopped/MEM_ACCESS mode or unaligned data");
            chip_sram[spi_address-'h6000]=shift[15:4];
        end else if(spi_address < 128) chip_reg[spi_address]=shift[15:0];
        else $fatal(1,"Unexpected register address");
        if(init_done) begin
            if(trigger !== 1) $fatal(1,"Runtime SPI wrote while TRIGGER was low");
            if((spi_address >= 'h65cd && spi_address <= 'h6fff) ||
                spi_address == 'h22 || spi_address == 'h32 ||
                spi_address == 'h28 || spi_address == 'h29 ||
                spi_address == 'h51 || spi_address == 'h52)
                $fatal(1,"Runtime command modified DAC4 or global timing");
        end
        writes=writes+1;
    end
    always @(posedge sys_clk) if(sys_resetn) begin
        if(dut.design_1_i.uart_cmd_rx_0_data_valid) rx_events=rx_events+1;
        if(dut.design_1_i.uart_cmd_rx_0_frame_error) frame_errors=frame_errors+1;
        if(dut.design_1_i.AD9106_0_cfg_done && dut.design_1_i.ad9106_cmd_parser_0_cfg_last)
            last_cfg_seen=1;
        if(dut.design_1_i.ad9106_cmd_parser_0_rsp_valid &&
           dut.design_1_i.ad9106_cmd_parser_0_rsp_status == 0 &&
           (dut.design_1_i.ad9106_cmd_parser_0_rsp_cmd <= 3 ||
            dut.design_1_i.ad9106_cmd_parser_0_rsp_cmd == 'h42 ||
            dut.design_1_i.ad9106_cmd_parser_0_rsp_cmd == 'h43)) begin
            if(!last_cfg_seen || trigger !== 0 || cs_n !== 1)
                $fatal(1,"Success reply preceded final cfg_done/trigger restart");
        end
        if(dut.design_1_i.uart_cmd_tx_0_done) tx_events=tx_events+1;
    end
    initial forever begin
        @(negedge uart_tx);
        #(BIT_NS/2);
        if(uart_tx !== 0) $fatal(1,"UART TX false start");
        for(j=0;j<8;j=j+1) begin #(BIT_NS); decoded[j]=uart_tx; end
        #(BIT_NS);
        if(uart_tx !== 1) $fatal(1,"UART TX stop bit missing");
        reply[replies]=decoded; replies=replies+1;
    end
    task send_byte(input [7:0] value);
        integer b;
        begin
            uart_rx=0; #(BIT_NS);
            for(b=0;b<8;b=b+1) begin uart_rx=value[b]; #(BIT_NS); end
            uart_rx=1; #(BIT_NS);
        end
    endtask
    task new_request(input [7:0] seq, input [7:0] cmd);
        integer k;
        begin
            for(k=0;k<24;k=k+1) request[k]=0;
            request[0]='haa; request[1]='h55; request[2]=seq; request[3]=cmd;
            request[4]=1; request[5]=4; request[11]=1; request[23]='h0d;
            last_cfg_seen=0; command_start=$realtime;
        end
    endtask
    task checksum_request;
        integer k;
        begin
            request[22]=0;
            for(k=2;k<22;k=k+1) request[22]=request[22]^request[k];
        end
    endtask
    task send_request;
        integer k;
        begin for(k=0;k<24;k=k+1) send_byte(request[k]); end
    endtask
    task expect_reply(input [7:0] seq, input [7:0] cmd, input [7:0] status);
        begin
            wait(replies >= reply_read+8);
            if(reply[reply_read] !== 'h55 || reply[reply_read+1] !== 'haa ||
               reply[reply_read+2] !== seq || reply[reply_read+3] !== cmd ||
               reply[reply_read+4] !== status || reply[reply_read+5] !== (seq^cmd^status) ||
               reply[reply_read+6] !== 'h0d || reply[reply_read+7] !== 'h0a)
                $fatal(1,"Reply mismatch seq=%0d cmd=%0d expected=%0d actual=%0d",
                       seq,cmd,status,reply[reply_read+4]);
            reply_read=reply_read+8;
            wait(dut.design_1_i.uart_cmd_tx_0_done);
            repeat(5) @(posedge sys_clk);
            transaction_checks=transaction_checks+1;
            elapsed_ms=($realtime-command_start)/1000000.0;
            $display("PASS TOP: reply seq=%0d cmd=%0d status=%0d, elapsed=%.3f ms, writes=%0d",
                     seq,cmd,status,elapsed_ms,writes);
            $fdisplay(event_fd,"%0.3f,reply,%0d,%0d,%0d,%0d",$realtime,seq,cmd,status,writes);
        end
    endtask
    task check_write(input integer index, input [14:0] addr, input [15:0] data);
        begin
            if(wr_addr[index] !== addr || wr_data[index] !== data)
                $fatal(1,"SPI[%0d]: expected %h/%h actual %h/%h",index,addr,data,
                       wr_addr[index],wr_data[index]);
        end
    endtask
    task check_init;
        integer k, n, level;
        begin
            if(writes != 3011 || init_busy !== 0 || trigger !== 0 || clken !== 1 || dac_reset !== 1)
                $fatal(1,"Top initialization/control pins failed");
            for(k=0;k<1485;k=k+1) begin
                check_write(1+k,'h6000+k,((k*50)%1485<743)?16'h4000:16'hc000);
                n=(k%297)/3;
                if(n==0 || n==98) level=0;
                else if(n<25) level=n*42;
                else if(n<50) level=24*42-(n-24)*16;
                else if(n<75) level=24*42-25*16-(n-49)*69;
                else level=24*42-25*16-25*69+(n-74)*45;
                check_write(1486+k,'h65cd+k,(level&4095)<<4);
                saved_arb[k]=chip_sram[1485+k];
            end
            check_write(2978,'h29,1485);
            check_write(2991,'h3e,'h113d); check_write(2992,'h3f,'h3300);
            check_write(3002,'h51,'h5cd0); check_write(3003,'h52,'hb990);
            check_write(3006,'h56,'h5cc0);
            check_write(3010,'h1d,1);
            init_checks=init_checks+1;
            $display("PASS TOP: initialization %0d, 3011 writes, all 2970 SRAM samples, DAC4 five periods",init_checks);
            $fdisplay(event_fd,"%0.3f,init,0,0,0,%0d",$realtime,writes);
        end
    endtask
    task check_square(input integer cycles, input integer duty_code, input [11:0] hi, input [11:0] lo);
        integer k, edges, high_count, signed_code;
        reg previous_high, is_high;
        reg [11:0] expected;
        begin
            if(writes != base+1492) $fatal(1,"Square transaction count");
            edges=0; high_count=0;
            previous_high=(chip_sram[1484] == hi);
            wave_fd=$fopen($sformatf("square_%0dkhz.csv",cycles*100),"w");
            $fdisplay(wave_fd,"sample,time_us,dac_sram_code");
            for(k=0;k<1485;k=k+1) begin
                expected=((k*cycles)%1485<duty_code)?hi:lo;
                if(chip_sram[k] !== expected) $fatal(1,"Square SRAM mismatch at %0d",k);
                if(chip_sram[1485+k] !== saved_arb[k]) $fatal(1,"DAC4 data changed");
                is_high=(chip_sram[k] == hi);
                if(is_high && !previous_high) edges=edges+1;
                if(is_high) high_count=high_count+1;
                previous_high=is_high;
                signed_code=$signed(chip_sram[k]);
                $fdisplay(wave_fd,"%0d,%.9f,%0d",k,k/148.5,signed_code);
            end
            $fclose(wave_fd);
            if(edges != cycles) $fatal(1,"Square output cycles expected=%0d actual=%0d",cycles,edges);
            check_write(base,'h1e,0); check_write(base+1,'h1e,4);
            check_write(base+1487,'h1e,0); check_write(base+1490,'h1e,1);
            check_write(base+1491,'h1d,1);
            $display("PASS TOP: square %.1f kHz, %0d cycles/10 us, high fraction %.4f%%",
                     cycles*100.0,edges,high_count*100.0/1485);
        end
    endtask

    initial begin #1500000000; $fatal(1,"Top-level test timeout"); end
    initial begin
        #1000; resetn=1;
        wait(sys_resetn === 1); repeat(10) @(posedge sys_clk);
        clock_start=$realtime; @(posedge sys_clk);
        if($realtime-clock_start < 9.99 || $realtime-clock_start > 10.01)
            $fatal(1,"Clock Wizard output is not 100 MHz");
        $display("PASS TOP: clock block locked, 50 MHz input -> 100 MHz system");
        new_request(0,1); checksum_request; send_request; expect_reply(0,1,7);
        wait(init_done === 1); repeat(10) @(posedge sys_clk); check_init;

        base=writes; new_request(1,1);
        request[5]=2; request[7]=15; request[8]=128;
        request[9]='h20; request[10]=0; request[11]=0; request[12]='h40;
        checksum_request; send_request; expect_reply(1,1,0);
        if(writes != base+8) $fatal(1,"Sine transaction count");
        check_write(base+1,'h35,'h2000); check_write(base+2,'h25,'hf800);
        check_write(base+3,'h3e,'h2000); check_write(base+4,'h3f,0);
        check_write(base+5,'h43,'h4000); check_write(base+7,'h1d,1);
        $display("PASS TOP: sine frequency word=0x200000 (18.5625 MHz), phase=90 deg, gain=0.5, offset=-128");

        base=writes; new_request(2,2); request[5]=12; request[8]=128; request[11]=63;
        checksum_request; send_request; expect_reply(2,2,0);
        if(writes != base+6) $fatal(1,"Triangle transaction count");
        check_write(base+1,'h34,'hc000); check_write(base+2,'h24,'h0800);
        check_write(base+3,'h37,'hfe07); check_write(base+5,'h1d,1);
        $display("PASS TOP: triangle step=63, gain=-1, offset=128");

        base=writes; new_request(3,3); request[5]=2;
        request[14]=2; request[15]=231; request[16]=6; request[18]=10;
        checksum_request; send_request; expect_reply(3,3,0);
        check_square(1,743,'h600,'ha00); check_write(base+1488,'h33,'h2000);

        base=writes; new_request(4,3); request[11]=2;
        request[14]=1; request[15]=115; request[16]=4; request[18]=12;
        checksum_request; send_request; expect_reply(4,3,0);
        check_square(2,371,'h400,'hc00);

        base=writes; new_request(5,3); request[10]=2; request[11]=230;
        request[14]=2; request[15]=231; request[16]=7; request[17]=255; request[18]=8;
        checksum_request; send_request; expect_reply(5,3,0);
        check_square(742,743,'h7ff,'h800);

        base=writes; new_request(6,1); request[4]=0; request[7]=1;
        checksum_request; send_request; expect_reply(6,1,0);
        if(writes != base+8) $fatal(1,"Mute transaction count");
        check_write(base+1,'h35,0); check_write(base+2,'h25,0);

        base=writes;
        new_request(10,1); checksum_request; request[22]=request[22]^1;
        send_request; expect_reply(10,1,2);
        new_request(11,4); checksum_request; send_request; expect_reply(11,4,3);
        new_request(12,3); request[10]=2; request[11]=231; request[14]=2; request[15]=231;
        checksum_request; send_request; expect_reply(12,3,4);
        new_request(13,1); checksum_request; request[23]=0;
        send_request; expect_reply(13,1,1);
        new_request(14,1);
        send_byte('haa); send_byte('h55); send_byte(14); send_byte(1);
        expect_reply(14,1,5);
        new_request(15,1);
        send_byte('haa); send_byte('h55); send_byte(15); send_byte(1);
        uart_rx=0; #(BIT_NS*12); uart_rx=1;
        expect_reply(15,1,6);
        if(writes != base) $fatal(1,"Bad command caused an SPI write");
        if(frame_errors != 1) $fatal(1,"Break should produce exactly one frame error");

        base=writes; new_request(16,3); request[11]=3;
        request[14]=2; request[15]=231; request[16]=4; request[18]=12;
        checksum_request; send_request; expect_reply(16,3,0);
        check_square(3,743,'h400,'hc00);

        // Assert the actual external reset while a runtime SRAM SPI frame is active.
        new_request(17,3); request[14]=2; request[15]=231;
        request[16]=4; request[18]=12; checksum_request; send_request;
        wait(!cs_n && dut.design_1_i.ad9106_cmd_parser_0_cfg_addr >= 'h6000);
        #1000; resetn=0; uart_rx=1;
        #2000; writes=0; bits=0; resetn=1;
        wait(init_done === 0); wait(init_done === 1);
        repeat(10) @(posedge sys_clk); check_init;
        if(uart_tx !== 1) $fatal(1,"UART TX not idle after reset");
        base=writes; new_request(18,1); checksum_request; send_request; expect_reply(18,1,0);
        if(writes != base+8) $fatal(1,"Command after reset failed");
        $display("PASS TOP SUMMARY: %0d replies; %0d initializations; RX bytes=%0d TX done=%0d UART errors=%0d",
                 transaction_checks,init_checks,rx_events,tx_events,frame_errors);
        $fclose(spi_fd); $fclose(event_fd);
        $finish;
    end
endmodule
