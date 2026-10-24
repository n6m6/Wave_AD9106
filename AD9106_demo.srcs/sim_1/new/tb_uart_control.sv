`timescale 1ns / 1ps
module tb_uart_control;
    localparam DIV=16;
    reg clk=0, resetn=0, uart_rx=1;
    always #5 clk=~clk;
    wire [7:0] rx_data;
    wire rx_valid, rx_error, cfg_valid, cfg_ready, cfg_last, cfg_done;
    wire [14:0] cfg_addr;
    wire [15:0] cfg_wdata;
    wire rsp_valid, rsp_ready, rsp_done, parser_busy, tx_busy, uart_tx;
    wire [7:0] rsp_seq, rsp_cmd, rsp_status;
    wire sclk, sdio, cs_n, dac_reset, trigger, clken, init_done, init_busy;
    integer writes=0, bits=0, replies=0, reply_read=0;
    integer base, i, j, point, arb_code;
    reg [31:0] shift=0;
    reg [14:0] addresses [0:16383];
    reg [15:0] values [0:16383];
    reg [7:0] reply_bytes [0:1023];
    reg [7:0] request [0:23];
    reg [7:0] tx_byte;

    uart_cmd_rx #(.SYS_CLK_HZ(16000000), .BAUD_RATE(1000000)) rx_i
        (.clk(clk),.resetn(resetn),.uart_rx(uart_rx),.data(rx_data),
         .data_valid(rx_valid),.frame_error(rx_error));
    ad9106_cmd_parser #(.SYS_CLK_HZ(16000000), .FRAME_TIMEOUT_CYCLES(1000)) parser_i
        (.clk(clk),.resetn(resetn),.rx_data(rx_data),.rx_valid(rx_valid),
         .rx_error(rx_error),.init_done(init_done),.cfg_valid(cfg_valid),
         .cfg_ready(cfg_ready),.cfg_addr(cfg_addr),.cfg_wdata(cfg_wdata),
         .cfg_last(cfg_last),.cfg_done(cfg_done),.rsp_valid(rsp_valid),
         .rsp_ready(rsp_ready),.rsp_seq(rsp_seq),.rsp_cmd(rsp_cmd),
         .rsp_status(rsp_status),.rsp_done(rsp_done),.busy(parser_busy));
    uart_cmd_tx #(.SYS_CLK_HZ(16000000),.BAUD_RATE(1000000)) tx_i
        (.clk(clk),.resetn(resetn),.rsp_valid(rsp_valid),.rsp_ready(rsp_ready),
         .rsp_seq(rsp_seq),.rsp_cmd(rsp_cmd),.rsp_status(rsp_status),
         .uart_tx(uart_tx),.busy(tx_busy),.done(rsp_done));
    AD9106 #(.SYS_CLK_HZ(16000000),.SPI_CLK_HZ(8000000),
        .RESET_LOW_CYCLES(2),.RESET_HIGH_CYCLES(2),
        .RUNTIME_UPDATE_CYCLES(4)) dac_i
        (.clk(clk),.resetn(resetn),.ad9106_sclk(sclk),.ad9106_sdio(sdio),
         .ad9106_sdo(1'b0),.ad9106_cs_n(cs_n),.ad9106_reset(dac_reset),
         .ad9106_trigger(trigger),.ad9106_clken(clken),.init_done(init_done),
         .init_busy(init_busy),.cfg_valid(cfg_valid),.cfg_ready(cfg_ready),
         .cfg_addr(cfg_addr),.cfg_wdata(cfg_wdata),.cfg_last(cfg_last),.cfg_done(cfg_done));

    always @(negedge cs_n) begin bits=0; shift=0; end
    always @(posedge sclk) if (!cs_n) begin
        shift={shift[30:0],sdio};
        bits=bits+1;
    end
    always @(posedge cs_n) if (resetn && bits != 0) begin
        if (bits != 32 || shift[31]) $fatal(1,"Malformed SPI transaction");
        addresses[writes]=shift[30:16]; values[writes]=shift[15:0];
        if (writes >= 3011) begin
            if (!trigger) $fatal(1,"Trigger must stay high during runtime writes");
            if ((shift[30:16] >= 15'h65cd && shift[30:16] <= 15'h6fff) ||
                shift[30:16] == 15'h0022 || shift[30:16] == 15'h0032 ||
                shift[30:16] == 15'h0028 || shift[30:16] == 15'h0029)
                $fatal(1,"Command modified DAC4/shared timing");
        end
        writes=writes+1;
    end
    always @(posedge clk) if (resetn && rsp_valid && rsp_status == 0) begin
        if (trigger || !cfg_ready || addresses[writes-1] != 15'h001d ||
            values[writes-1] != 1)
            $fatal(1,"Success response before SPI/update/trigger completion");
    end

    initial forever begin
        @(negedge uart_tx);
        repeat(DIV/2) @(posedge clk);
        if (uart_tx !== 0) $fatal(1,"TX start bit");
        for (j=0;j<8;j=j+1) begin
            repeat(DIV) @(posedge clk);
            tx_byte[j]=uart_tx;
        end
        repeat(DIV) @(posedge clk);
        if (uart_tx !== 1) $fatal(1,"TX stop bit");
        reply_bytes[replies]=tx_byte;
        replies=replies+1;
    end

    task send_byte(input [7:0] value);
        integer b;
        begin
            @(negedge clk); uart_rx=0;
            repeat(DIV) @(negedge clk);
            for(b=0;b<8;b=b+1) begin
                uart_rx=value[b]; repeat(DIV) @(negedge clk);
            end
            uart_rx=1; repeat(DIV) @(negedge clk);
        end
    endtask
    task new_request(input [7:0] seq, input [7:0] cmd);
        integer k;
        begin
            for(k=0;k<24;k=k+1) request[k]=0;
            request[0]=8'haa; request[1]=8'h55;
            request[2]=seq; request[3]=cmd;
            request[4]=1; request[5]=4; request[11]=1; request[23]=8'h0d;
        end
    endtask
    task checksum_request;
        integer k;
        begin
            request[22]=0;
            for(k=2;k<=21;k=k+1) request[22]=request[22]^request[k];
        end
    endtask
    task send_request;
        integer k;
        begin for(k=0;k<24;k=k+1) send_byte(request[k]); end
    endtask
    task expect_reply(input [7:0] seq, input [7:0] cmd, input [7:0] status);
        begin
            wait(replies >= reply_read+8);
            if (reply_bytes[reply_read] !== 8'h55 || reply_bytes[reply_read+1] !== 8'haa ||
                reply_bytes[reply_read+2] !== seq || reply_bytes[reply_read+3] !== cmd ||
                reply_bytes[reply_read+4] !== status ||
                reply_bytes[reply_read+5] !== (seq^cmd^status) ||
                reply_bytes[reply_read+6] !== 8'h0d || reply_bytes[reply_read+7] !== 8'h0a)
                $fatal(1,"Reply mismatch: seq=%h cmd=%h expected status=%h got=%h",
                       seq,cmd,status,reply_bytes[reply_read+4]);
            reply_read=reply_read+8;
            wait(!parser_busy); repeat(3) @(negedge clk);
        end
    endtask
    task check_write(input integer index, input [14:0] addr, input [15:0] data);
        begin
            if (addresses[index] !== addr || values[index] !== data)
                $fatal(1,"SPI[%0d]: expected %h/%h, got %h/%h",index,addr,data,
                       addresses[index],values[index]);
        end
    endtask
    task check_square(input integer start_index, input integer cycles,
                      input integer duty_code, input [15:0] high_code, input [15:0] low_code);
        integer k, rising_edges;
        reg current_high, previous_high;
        begin
            rising_edges=0;
            previous_high=(((1484*cycles)%1485)<duty_code);
            for(k=0;k<1485;k=k+1) begin
                current_high=(((k*cycles)%1485)<duty_code);
                check_write(start_index+2+k,15'h6000+k,current_high?high_code:low_code);
                if(current_high && !previous_high) rising_edges=rising_edges+1;
                previous_high=current_high;
            end
            if(rising_edges != cycles) $fatal(1,"Square cycle count: expected %0d got %0d",cycles,rising_edges);
            check_write(start_index+1487,15'h001e,0);
            check_write(start_index+1490,15'h001e,1);
            check_write(start_index+1491,15'h001d,1);
        end
    endtask

    initial begin
        #20000000; $fatal(1,"Simulation timeout");
    end
    initial begin
        repeat(5) @(negedge clk); resetn=1;
        // Full valid command during initialization must be rejected, not applied.
        new_request(0,1); checksum_request; send_request; expect_reply(0,1,7);
        wait(init_done); repeat(4) @(negedge clk);
        if(writes != 3011 || init_busy || trigger) $fatal(1,"Initialization regression");
        for(i=0;i<1485;i=i+1) begin
            check_write(1+i,15'h6000+i,((i*50)%1485<743)?16'h4000:16'hc000);
            // Original 99-point waveform, each point held for three samples;
            // verify all five copies independently of the DUT's accumulators.
            point=(i%297)/3;
            if(point==0 || point==98) arb_code=0;
            else if(point<25) arb_code=point*42;
            else if(point<50) arb_code=24*42-(point-24)*16;
            else if(point<75) arb_code=24*42-25*16-(point-49)*69;
            else arb_code=24*42-25*16-25*69+(point-74)*45;
            check_write(1486+i,15'h65cd+i,(arb_code&4095)<<4);
        end
        check_write(2978,15'h0029,16'd1485);
        check_write(2991,15'h003e,16'h113d);
        check_write(2992,15'h003f,16'h3300);
        check_write(3002,15'h0051,16'h5cd0);
        check_write(3003,15'h0052,16'hb990);
        check_write(3006,15'h0056,16'h5cc0);

        base=writes;
        new_request(1,1);
        request[7]=8'h0f; request[8]=8'h80; // signed offset -128
        request[9]=8'h11; request[10]=8'h3d; request[11]=8'h33;
        request[12]=8'h40;
        checksum_request; send_request; expect_reply(1,1,0);
        if(writes != base+8 || trigger) $fatal(1,"Sine completion");
        check_write(base,15'h001e,0); check_write(base+1,15'h0035,16'h4000);
        check_write(base+2,15'h0025,16'hf800);
        check_write(base+3,15'h003e,16'h113d); check_write(base+4,15'h003f,16'h3300);
        check_write(base+5,15'h0043,16'h4000);
        check_write(base+6,15'h001e,1); check_write(base+7,15'h001d,1);

        base=writes;
        new_request(2,2); request[11]=63; request[5]=8'h0c;
        checksum_request; send_request; expect_reply(2,2,0);
        if(writes != base+6) $fatal(1,"Triangle write count");
        check_write(base+1,15'h0034,16'hc000);
        check_write(base+3,15'h0037,16'hfe07);
        check_write(base+4,15'h001e,1); check_write(base+5,15'h001d,1);

        base=writes;
        new_request(3,3); request[11]=50; request[14]=2; request[15]=231;
        request[16]=4; request[18]=12;
        checksum_request; send_request; expect_reply(3,3,0);
        if(writes != base+1492) $fatal(1,"Square write count");
        check_write(base,15'h001e,0); check_write(base+1,15'h001e,4);
        check_square(base,50,743,16'h4000,16'hc000);
        check_write(base+1488,15'h0033,16'h4000);
        check_write(base+1489,15'h0023,0);

        base=writes;
        new_request(4,1); request[4]=0; request[7]=1;
        checksum_request; send_request; expect_reply(4,1,0);
        check_write(base+1,15'h0035,0); check_write(base+2,15'h0025,0);

        base=writes;
        new_request(5,1); checksum_request; request[22]=request[22]^1;
        send_request; expect_reply(5,1,2);
        new_request(6,4); checksum_request; send_request; expect_reply(6,4,3);
        new_request(7,2); request[11]=0;
        checksum_request; send_request; expect_reply(7,2,4);
        new_request(8,3); request[10]=2; request[11]=231; request[14]=2; request[15]=231;
        checksum_request; send_request; expect_reply(8,3,4);
        new_request(9,1); request[5]=8'h10;
        checksum_request; send_request; expect_reply(9,1,4);
        new_request(14,3); request[10]=2; request[11]=230; request[14]=5; request[15]=204;
        checksum_request; send_request; expect_reply(14,3,4);
        new_request(10,1); checksum_request; request[23]=0;
        send_request; expect_reply(10,1,1);
        send_byte(8'haa); send_byte(8'h55); send_byte(11); send_byte(1);
        expect_reply(11,1,5);
        // Bad stop bit within a frame, followed by idle recovery.
        send_byte(8'haa); send_byte(8'h55); send_byte(12); send_byte(1);
        @(negedge clk); uart_rx=0;
        repeat(DIV*11) @(negedge clk); uart_rx=1;
        expect_reply(12,1,6);
        if(writes != base) $fatal(1,"Rejected request caused writes");

        // Header overlap and recovery, then a legal boundary-rate square request.
        send_byte(8'haa);
        new_request(13,3); request[10]=2; request[11]=230; request[14]=2; request[15]=231;
        request[16]=7; request[17]=255; request[18]=8;
        checksum_request; send_request; expect_reply(13,3,0);
        if(writes != base+1492) $fatal(1,"Recovery failed");
        check_square(base,742,743,16'h7ff0,16'h8000);

        // 100/200/300 kHz: validate the new frequency grid and narrow duty limit.
        for(i=1;i<=3;i=i+1) begin
            base=writes;
            new_request(20+i,3); request[11]=i;
            request[14]=2; request[15]=231;
            request[16]=4; request[18]=12;
            if(i==3) begin request[14]=0; request[15]=3; end
            checksum_request; send_request; expect_reply(20+i,3,0);
            if(writes != base+1492) $fatal(1,"Low frequency write count");
            check_square(base,i,(i==3)?3:743,16'h4000,16'hc000);
        end
        $display("PASS: UART -> parser -> AD9106 SPI -> UART; init, all waveforms, mute, boundaries, errors and recovery");
        $finish;
    end
endmodule
