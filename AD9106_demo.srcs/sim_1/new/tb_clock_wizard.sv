`timescale 1ns / 1ps
// Bounded test of the actual generated top with the vendor MMCM model.
module tb_clock_wizard;
    reg clk_in=0, resetn=0;
    always #10 clk_in=~clk_in;
    wire tx, init_done, init_busy;
    design_1_wrapper dut(.clk_in(clk_in),.resetn(resetn),.uart_rx_0(1'b1),
        .uart_tx_0(tx),.ad9106_sdo_0(1'b0),.init_done_0(init_done),.init_busy_0(init_busy));
    wire clk100=dut.design_1_i.clk_wiz_clk_out1;
    wire locked=dut.design_1_i.clk_wiz_locked;
    realtime t_start;
    integer n;
    task check_clock;
        begin
            repeat(10) @(posedge clk100);
            for(n=0;n<10;n=n+1) begin
                t_start=$realtime; @(posedge clk100);
                if($realtime-t_start < 9.99 || $realtime-t_start > 10.01)
                    $fatal(1,"Vendor MMCM frequency mismatch");
            end
            if(tx !== 1 || init_done !== 0 || init_busy !== 1)
                $fatal(1,"Top startup state mismatch");
        end
    endtask
    initial begin #200000; $fatal(1,"Vendor clock lock timeout"); end
    initial begin
        #1000; resetn=1;
        wait(locked === 1); check_clock;
        $display("PASS CLOCK: vendor MMCM lock and 100 MHz output");
        resetn=0;
        #1000;
        if(locked !== 0) $fatal(1,"External reset did not clear MMCM lock");
        resetn=1;
        wait(locked === 1); check_clock;
        $display("PASS CLOCK: external reset, relock and top startup state");
        $display("PASS CLOCK SUMMARY: actual generated wrapper and vendor MMCM verified");
        $finish;
    end
endmodule
