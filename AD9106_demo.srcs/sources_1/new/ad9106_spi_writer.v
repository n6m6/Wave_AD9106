`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// AD9106 32-bit SPI write-only transaction engine.
//////////////////////////////////////////////////////////////////////////////////

module ad9106_spi_writer #(
    parameter integer SPI_HALF_DIV = 50
) (
    input  wire        clk,
    input  wire        resetn,
    input  wire        start,
    input  wire [14:0] addr,
    input  wire [15:0] wdata,
    input  wire        read_en,
    input  wire        sdo,
    output reg [15:0]  rdata,
    output reg         busy,
    output reg         done,
    output reg         sclk,
    output reg         sdio,
    output reg         cs_n
);

    reg [31:0] shifter;
    reg [5:0]  bit_index;
    reg [31:0] div_counter;

    always @(posedge clk) begin
        if (!resetn) begin
            busy        <= 1'b0;
            done        <= 1'b0;
            sclk        <= 1'b0;
            sdio        <= 1'b0;
            cs_n        <= 1'b1;
            shifter     <= 32'h00000000;
            bit_index   <= 6'd31;
            div_counter <= 32'd0;
            rdata       <= 16'd0;
        end else begin
            done <= 1'b0;

            if (start && !busy) begin
                shifter     <= {read_en, addr, wdata};
                rdata       <= 16'd0;
                bit_index   <= 6'd31;
                div_counter <= SPI_HALF_DIV - 1;
                busy        <= 1'b1;
                cs_n        <= 1'b0;
                sclk        <= 1'b0;
                sdio        <= read_en;
            end else if (busy) begin
                if (div_counter != 32'd0) begin
                    div_counter <= div_counter - 32'd1;
                end else begin
                    div_counter <= SPI_HALF_DIV - 1;

                    if (!sclk) begin
                        sclk <= 1'b1;
                        if (bit_index < 16)
                            rdata <= {rdata[14:0], sdo};
                    end else begin
                        sclk <= 1'b0;

                        if (bit_index == 6'd0) begin
                            busy <= 1'b0;
                            done <= 1'b1;
                            cs_n <= 1'b1;
                            sdio <= 1'b0;
                        end else begin
                            bit_index <= bit_index - 6'd1;
                            sdio      <= shifter[bit_index - 6'd1];
                        end
                    end
                end
            end
        end
    end

endmodule
