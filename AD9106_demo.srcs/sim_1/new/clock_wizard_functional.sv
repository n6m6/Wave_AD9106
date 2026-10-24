`timescale 1ns / 1ps
// Simulation-only 50 MHz -> 100 MHz functional clock model. Never add to
// synthesis sources. Replaces only the vendor clock primitive for fast logic
// regression; actual MMCM lock/reset behavior is checked in vendor-model tests.
module design_1_clk_wiz_0 (
    input wire clk_in1,
    input wire resetn,
    output reg clk_out1=0,
    output reg locked=0
);
    reg [6:0] lock_count=0;
    always @(posedge clk_in1) begin
        clk_out1=1; #5;
        clk_out1=0; #5;
        clk_out1=1; #5;
        clk_out1=0;
    end
    always @(posedge clk_in1 or negedge resetn) begin
        if(!resetn) begin locked<=0; lock_count<=0; end
        else if(lock_count == 63) locked<=1;
        else lock_count<=lock_count+1'b1;
    end
endmodule
