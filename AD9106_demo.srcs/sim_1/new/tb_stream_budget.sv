`timescale 1ns/1ps
// Read-only feasibility experiment: exercise the existing runtime SPI path.
// No AD9106 analog model; measurements end at cfg_done, including update wait.
module stream_budget_case #(parameter integer SPI_HZ=1000000)(output reg finished=0);
    reg clk=0, resetn=0, valid=0;
    reg [14:0] addr=0;
    reg [15:0] data=0;
    wire ready, done, initialized;
    integer n, ch, channels;
    realtime started;
    always #5 clk=~clk;
    AD9106 #(.SPI_CLK_HZ(SPI_HZ), .RESET_LOW_CYCLES(2), .RESET_HIGH_CYCLES(2)) dut(
        .clk(clk), .resetn(resetn), .ad9106_sdo(1'b0), .init_done(initialized),
        .cfg_valid(valid), .cfg_ready(ready), .cfg_addr(addr), .cfg_wdata(data),
        .cfg_last(1'b0), .cfg_done(done));
    task write_reg(input [14:0] address, input [15:0] value);
        begin
            @(negedge clk);
            while(!ready) @(negedge clk);
            addr=address; data=value; valid=1;
            @(negedge clk); valid=0;
            wait(done);
        end
    endtask
    initial begin
        #100; resetn=1; wait(initialized);
        // Continuous constants: stage four zero values then commit together.
        write_reg('h26,'h0101); write_reg('h27,'h0101);
        for(ch=0;ch<4;ch=ch+1) write_reg('h2e+ch,0);
        write_reg('h1d,1);
        for(channels=1;channels<=4;channels=channels+3) begin
            started=$realtime;
            for(n=0;n<20;n=n+1) begin
                for(ch=0;ch<channels;ch=ch+1) write_reg('h2e+ch,(n+ch)<<4);
                write_reg('h1d,1);
            end
            $display("STREAM_BUDGET spi_hz=%0d channels=%0d group_us=%0.3f",
                     SPI_HZ,channels,($realtime-started)/20000.0);
        end
        finished=1;
    end
endmodule

module tb_stream_budget;
    wire a,b,c,d;
    stream_budget_case #(.SPI_HZ(1000000)) c1(a);
    stream_budget_case #(.SPI_HZ(12500000)) c2(b);
    stream_budget_case #(.SPI_HZ(25000000)) c3(c);
    stream_budget_case #(.SPI_HZ(50000000)) c4(d);
    initial begin wait(a&&b&&c&&d); $display("PASS STREAM BUDGET (digital timing only)"); $finish; end
    initial begin #200000000; $fatal(1,"Budget simulation timeout"); end
endmodule
