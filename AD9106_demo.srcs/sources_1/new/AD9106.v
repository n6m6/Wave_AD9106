`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// AD9106 power-on demo controller.
//
// Board net names found in Netlist_Schematic3_2026-07-17.tel:
//   H2.1 TRIGGER, H2.2 SCLK, H2.3 SDIO, H2.4 SDO, H2.5 CS,
//   H2.6 RESET, H2.7 CLKEN.
//
// The module is intended for Vivado Block Design packaging.  It does not use AXI;
// after reset it writes a fixed SPI configuration into the AD9106 and then starts
// the pattern generator.  Default demo outputs:
//   DAC1/OUT1: DDS sine wave
//   DAC2/OUT2: triangle wave from the internal sawtooth generator
//   DAC3/OUT3: 500 kHz square wave from SRAM addresses 0x000..0x062
//   DAC4/OUT4: arbitrary waveform from SRAM addresses 0x063..0x0c5
//////////////////////////////////////////////////////////////////////////////////

module AD9106 #(
    parameter integer SYS_CLK_HZ        = 100000000,
    parameter integer SPI_CLK_HZ        = 1000000,
    parameter integer RESET_LOW_CYCLES  = 100000,
    parameter integer RESET_HIGH_CYCLES = 100000,

    // DDS tuning word = round(fout / fclk_dac * 2^24). Default is about 500 kHz
    // with the board 148.5 MHz AD9106 DAC clock oscillator.
    parameter [23:0] DDS_TUNING_WORD = 24'h00DCA9,

    // Digital gain is signed 12-bit fixed point in AD9106 format.
    // 12'h400 = +1.0, 12'h7ff is almost +2.0, 12'hc00 = -1.0.
    parameter [11:0] DAC1_DIG_GAIN = 12'h400,
    parameter [11:0] DAC2_DIG_GAIN = 12'h400,
    parameter [11:0] DAC3_DIG_GAIN = 12'h400,
    parameter [11:0] DAC4_DIG_GAIN = 12'h400,

    // SRAM waveform timing. 99 samples held for 3 DAC clocks each make one
    // 297-DAC-clock pattern period, so the SRAM channels repeat at 500 kHz
    // with the 148.5 MHz board oscillator.
    parameter [3:0]  SRAM_HOLD          = 4'd3,
    parameter [3:0]  PAT_PERIOD_BASE    = 4'd1,
    parameter [15:0] PATTERN_PERIOD     = 16'd297,

    // DAC2 triangle. ftri = fclk_dac / (2 * 16384 * TRI_SAW_STEP).
    parameter [5:0]  TRI_SAW_STEP       = 6'd4,

    // DAC3 square waveform samples, signed 12-bit AD9106 data.
    parameter [11:0] SQUARE_HIGH        = 12'h400,
    parameter [11:0] SQUARE_LOW         = 12'hc00
) (
    input  wire clk,
    input  wire resetn,

    output wire ad9106_sclk,
    output wire ad9106_sdio,
    input  wire ad9106_sdo,
    output wire ad9106_cs_n,
    output reg  ad9106_reset,
    output reg  ad9106_trigger,
    output reg  ad9106_clken,

    output reg  init_done,
    output wire init_busy
);

    localparam [14:0] REG_SPICONFIG    = 15'h0000;
    localparam [14:0] REG_POWERCONFIG  = 15'h0001;
    localparam [14:0] REG_CLOCKCONFIG  = 15'h0002;
    localparam [14:0] REG_RAMUPDATE    = 15'h001d;
    localparam [14:0] REG_PAT_STATUS   = 15'h001e;
    localparam [14:0] REG_PAT_TYPE     = 15'h001f;
    localparam [14:0] REG_PATTERN_DLY  = 15'h0020;
    localparam [14:0] REG_DAC4_DOF     = 15'h0022;
    localparam [14:0] REG_DAC3_DOF     = 15'h0023;
    localparam [14:0] REG_DAC2_DOF     = 15'h0024;
    localparam [14:0] REG_DAC1_DOF     = 15'h0025;
    localparam [14:0] REG_WAV4_3CONFIG = 15'h0026;
    localparam [14:0] REG_WAV2_1CONFIG = 15'h0027;
    localparam [14:0] REG_PAT_TIMEBASE = 15'h0028;
    localparam [14:0] REG_PAT_PERIOD   = 15'h0029;
    localparam [14:0] REG_DAC4_3PATX   = 15'h002a;
    localparam [14:0] REG_DAC2_1PATX   = 15'h002b;
    localparam [14:0] REG_DAC4_DGAIN   = 15'h0032;
    localparam [14:0] REG_DAC3_DGAIN   = 15'h0033;
    localparam [14:0] REG_DAC2_DGAIN   = 15'h0034;
    localparam [14:0] REG_DAC1_DGAIN   = 15'h0035;
    localparam [14:0] REG_SAW4_3CONFIG = 15'h0036;
    localparam [14:0] REG_SAW2_1CONFIG = 15'h0037;
    localparam [14:0] REG_DDS_TW32     = 15'h003e;
    localparam [14:0] REG_DDS_TW1      = 15'h003f;
    localparam [14:0] REG_DDS4_PW      = 15'h0040;
    localparam [14:0] REG_DDS3_PW      = 15'h0041;
    localparam [14:0] REG_DDS2_PW      = 15'h0042;
    localparam [14:0] REG_DDS1_PW      = 15'h0043;
    localparam [14:0] REG_TRIG_TW_SEL  = 15'h0044;
    localparam [14:0] REG_DDSX_CONFIG  = 15'h0045;
    localparam [14:0] REG_START_DLY4   = 15'h0050;
    localparam [14:0] REG_START_ADDR4  = 15'h0051;
    localparam [14:0] REG_STOP_ADDR4   = 15'h0052;
    localparam [14:0] REG_START_DLY3   = 15'h0054;
    localparam [14:0] REG_START_ADDR3  = 15'h0055;
    localparam [14:0] REG_STOP_ADDR3   = 15'h0056;
    localparam [14:0] REG_START_DLY2   = 15'h0058;
    localparam [14:0] REG_START_DLY1   = 15'h005c;
    localparam [14:0] REG_SRAM_BASE    = 15'h6000;

    localparam integer SRAM_SAMPLES_PER_PERIOD = 99;
    localparam [11:0] DAC3_SRAM_START = 12'h000;
    localparam [11:0] DAC3_SRAM_STOP  = 12'h062;
    localparam [11:0] DAC4_SRAM_START = 12'h063;
    localparam [11:0] DAC4_SRAM_STOP  = 12'h0c5;
    localparam integer SRAM_WORDS      = SRAM_SAMPLES_PER_PERIOD * 2;
    localparam integer CFG_WORDS       = 37;

    function integer max_int;
        input integer a;
        input integer b;
        begin
            max_int = (a > b) ? a : b;
        end
    endfunction

    localparam integer SPI_HALF_DIV = max_int(1, SYS_CLK_HZ / (SPI_CLK_HZ * 2));

    localparam [3:0] ST_RESET_LOW  = 4'd0;
    localparam [3:0] ST_RESET_HIGH = 4'd1;
    localparam [3:0] ST_MEM_ON     = 4'd2;
    localparam [3:0] ST_SRAM       = 4'd3;
    localparam [3:0] ST_MEM_OFF    = 4'd4;
    localparam [3:0] ST_CONFIG     = 4'd5;
    localparam [3:0] ST_RUN        = 4'd6;
    localparam [3:0] ST_UPDATE     = 4'd7;
    localparam [3:0] ST_DONE       = 4'd8;

    reg [3:0]  state;
    reg [31:0] wait_counter;
    reg [7:0]  cfg_index;
    reg [7:0]  sram_index;
    reg [11:0] sram_sample;
    reg        issue_spi;
    reg [14:0] issue_addr;
    reg [15:0] issue_data;
    reg [30:0] cfg_current;

    wire       spi_busy;
    reg        spi_start;
    reg [14:0] spi_addr;
    reg [15:0] spi_wdata;
    wire       spi_done;

    assign init_busy = (state != ST_DONE);

    function [15:0] pack12;
        input [11:0] value;
        begin
            pack12 = {value, 4'h0};
        end
    endfunction

    function [15:0] pack_addr12;
        input [11:0] value;
        begin
            pack_addr12 = {value, 4'h0};
        end
    endfunction

    function [11:0] square_sample;
        input [7:0] index;
        begin
            square_sample = (index < ((SRAM_SAMPLES_PER_PERIOD + 1) / 2)) ?
                            SQUARE_HIGH : SQUARE_LOW;
        end
    endfunction

    function [11:0] next_sram_sample;
        input [7:0] index;
        input [11:0] current_sample;
        reg [7:0] next_index;
        begin
            next_index = index + 8'd1;

            if (next_index < SRAM_SAMPLES_PER_PERIOD)
                next_sram_sample = square_sample(next_index);
            else if (next_index == SRAM_SAMPLES_PER_PERIOD)
                next_sram_sample = 12'h000;
            else if (next_index < 8'd124)
                next_sram_sample = current_sample + 12'h02a;
            else if (next_index < 8'd149)
                next_sram_sample = current_sample - 12'h010;
            else if (next_index < 8'd174)
                next_sram_sample = current_sample - 12'h045;
            else if (next_index < 8'd197)
                next_sram_sample = current_sample + 12'h02d;
            else
                next_sram_sample = 12'h000;
        end
    endfunction

    function [30:0] cfg_word;
        input [7:0] index;
        begin
            case (index)
                8'd0:  cfg_word = {REG_SPICONFIG,    16'h0000}; // 4-wire, MSB first.
                8'd1:  cfg_word = {REG_POWERCONFIG,  16'h0000}; // All DACs active, internal references on.
                8'd2:  cfg_word = {REG_CLOCKCONFIG,  16'h0000};
                8'd3:  cfg_word = {REG_PAT_TYPE,     16'h0000}; // Continuous pattern.
                8'd4:  cfg_word = {REG_PATTERN_DLY,  16'h000e}; // Minimum trigger-to-output delay.
                8'd5:  cfg_word = {REG_PAT_TIMEBASE, {4'h0, SRAM_HOLD, PAT_PERIOD_BASE, 4'h1}};
                8'd6:  cfg_word = {REG_PAT_PERIOD,   PATTERN_PERIOD};
                8'd7:  cfg_word = {REG_DAC4_3PATX,   16'h0101};
                8'd8:  cfg_word = {REG_DAC2_1PATX,   16'h0101};
                8'd9:  cfg_word = {REG_DAC4_DOF,     16'h0000};
                8'd10: cfg_word = {REG_DAC3_DOF,     16'h0000};
                8'd11: cfg_word = {REG_DAC2_DOF,     16'h0000};
                8'd12: cfg_word = {REG_DAC1_DOF,     16'h0000};
                8'd13: cfg_word = {REG_DAC4_DGAIN,   pack12(DAC4_DIG_GAIN)};
                8'd14: cfg_word = {REG_DAC3_DGAIN,   pack12(DAC3_DIG_GAIN)};
                8'd15: cfg_word = {REG_DAC2_DGAIN,   pack12(DAC2_DIG_GAIN)};
                8'd16: cfg_word = {REG_DAC1_DGAIN,   pack12(DAC1_DIG_GAIN)};
                8'd17: cfg_word = {REG_SAW4_3CONFIG, 16'h0000};
                8'd18: cfg_word = {REG_SAW2_1CONFIG, {TRI_SAW_STEP, 2'b10, 6'd1, 2'b11}};
                8'd19: cfg_word = {REG_DDS_TW32,     DDS_TUNING_WORD[23:8]};
                8'd20: cfg_word = {REG_DDS_TW1,      {DDS_TUNING_WORD[7:0], 8'h00}};
                8'd21: cfg_word = {REG_DDS4_PW,      16'h0000};
                8'd22: cfg_word = {REG_DDS3_PW,      16'h0000};
                8'd23: cfg_word = {REG_DDS2_PW,      16'h0000};
                8'd24: cfg_word = {REG_DDS1_PW,      16'h0000};
                8'd25: cfg_word = {REG_TRIG_TW_SEL,  16'h0000};
                8'd26: cfg_word = {REG_DDSX_CONFIG,  16'h0000}; // DDS sine, SRAM address by DAC clock.
                8'd27: cfg_word = {REG_WAV4_3CONFIG, 16'h0000}; // DAC4/DAC3 from SRAM.
                8'd28: cfg_word = {REG_WAV2_1CONFIG, 16'h1131}; // DAC2 triangle, DAC1 DDS sine.
                8'd29: cfg_word = {REG_START_DLY4,   16'h0000};
                8'd30: cfg_word = {REG_START_ADDR4,  pack_addr12(DAC4_SRAM_START)};
                8'd31: cfg_word = {REG_STOP_ADDR4,   pack_addr12(DAC4_SRAM_STOP)};
                8'd32: cfg_word = {REG_START_DLY3,   16'h0000};
                8'd33: cfg_word = {REG_START_ADDR3,  pack_addr12(DAC3_SRAM_START)};
                8'd34: cfg_word = {REG_STOP_ADDR3,   pack_addr12(DAC3_SRAM_STOP)};
                8'd35: cfg_word = {REG_START_DLY2,   16'h0000};
                8'd36: cfg_word = {REG_START_DLY1,   16'h0000};
                default: cfg_word = {REG_SPICONFIG,  16'h0000};
            endcase
        end
    endfunction

    always @(*) begin
        issue_spi  = 1'b0;
        issue_addr = 15'h0000;
        issue_data = 16'h0000;
        cfg_current = cfg_word(cfg_index);

        case (state)
            ST_MEM_ON: begin
                issue_spi  = 1'b1;
                issue_addr = REG_PAT_STATUS;
                issue_data = 16'h0004; // MEM_ACCESS = 1, RUN = 0.
            end

            ST_SRAM: begin
                issue_spi  = 1'b1;
                issue_addr = REG_SRAM_BASE + {7'd0, sram_index};
                issue_data = pack12(sram_sample);
            end

            ST_MEM_OFF: begin
                issue_spi  = 1'b1;
                issue_addr = REG_PAT_STATUS;
                issue_data = 16'h0000;
            end

            ST_CONFIG: begin
                issue_spi  = 1'b1;
                issue_addr = cfg_current[30:16];
                issue_data = cfg_current[15:0];
            end

            ST_RUN: begin
                issue_spi  = 1'b1;
                issue_addr = REG_PAT_STATUS;
                issue_data = 16'h0001; // RUN = 1.
            end

            ST_UPDATE: begin
                issue_spi  = 1'b1;
                issue_addr = REG_RAMUPDATE;
                issue_data = 16'h0001; // Self-clearing.
            end

            default: begin
                issue_spi  = 1'b0;
                issue_addr = 15'h0000;
                issue_data = 16'h0000;
            end
        endcase
    end

    always @(posedge clk) begin
        if (!resetn) begin
            state          <= ST_RESET_LOW;
            wait_counter   <= 32'd0;
            cfg_index      <= 8'd0;
            sram_index     <= 8'd0;
            sram_sample    <= SQUARE_HIGH;
            spi_start      <= 1'b0;
            spi_addr       <= 15'h0000;
            spi_wdata      <= 16'h0000;
            ad9106_reset   <= 1'b0;
            ad9106_trigger <= 1'b1;
            ad9106_clken   <= 1'b1;
            init_done      <= 1'b0;
        end else begin
            spi_start    <= 1'b0;
            ad9106_clken <= 1'b1;

            case (state)
                ST_RESET_LOW: begin
                    ad9106_reset   <= 1'b0;
                    ad9106_trigger <= 1'b1;
                    init_done      <= 1'b0;

                    if (wait_counter >= RESET_LOW_CYCLES[31:0]) begin
                        wait_counter <= 32'd0;
                        state        <= ST_RESET_HIGH;
                    end else begin
                        wait_counter <= wait_counter + 32'd1;
                    end
                end

                ST_RESET_HIGH: begin
                    ad9106_reset <= 1'b1;

                    if (wait_counter >= RESET_HIGH_CYCLES[31:0]) begin
                        wait_counter <= 32'd0;
                        state        <= ST_MEM_ON;
                    end else begin
                        wait_counter <= wait_counter + 32'd1;
                    end
                end

                ST_MEM_ON: begin
                    if (issue_spi && !spi_busy && !spi_start && !spi_done) begin
                        spi_addr  <= issue_addr;
                        spi_wdata <= issue_data;
                        spi_start <= 1'b1;
                    end
                    if (spi_done)
                        state <= ST_SRAM;
                end

                ST_SRAM: begin
                    if (issue_spi && !spi_busy && !spi_start && !spi_done) begin
                        spi_addr  <= issue_addr;
                        spi_wdata <= issue_data;
                        spi_start <= 1'b1;
                    end
                    if (spi_done) begin
                        if (sram_index == SRAM_WORDS - 1) begin
                            sram_index <= 8'd0;
                            sram_sample <= SQUARE_HIGH;
                            state      <= ST_MEM_OFF;
                        end else begin
                            sram_sample <= next_sram_sample(sram_index, sram_sample);
                            sram_index <= sram_index + 8'd1;
                        end
                    end
                end

                ST_MEM_OFF: begin
                    if (issue_spi && !spi_busy && !spi_start && !spi_done) begin
                        spi_addr  <= issue_addr;
                        spi_wdata <= issue_data;
                        spi_start <= 1'b1;
                    end
                    if (spi_done)
                        state <= ST_CONFIG;
                end

                ST_CONFIG: begin
                    if (issue_spi && !spi_busy && !spi_start && !spi_done) begin
                        spi_addr  <= issue_addr;
                        spi_wdata <= issue_data;
                        spi_start <= 1'b1;
                    end
                    if (spi_done) begin
                        if (cfg_index == CFG_WORDS - 1) begin
                            cfg_index <= 8'd0;
                            state     <= ST_RUN;
                        end else begin
                            cfg_index <= cfg_index + 8'd1;
                        end
                    end
                end

                ST_RUN: begin
                    if (issue_spi && !spi_busy && !spi_start && !spi_done) begin
                        spi_addr  <= issue_addr;
                        spi_wdata <= issue_data;
                        spi_start <= 1'b1;
                    end
                    if (spi_done)
                        state <= ST_UPDATE;
                end

                ST_UPDATE: begin
                    if (issue_spi && !spi_busy && !spi_start && !spi_done) begin
                        spi_addr  <= issue_addr;
                        spi_wdata <= issue_data;
                        spi_start <= 1'b1;
                    end
                    if (spi_done) begin
                        ad9106_trigger <= 1'b0;
                        init_done      <= 1'b1;
                        state          <= ST_DONE;
                    end
                end

                ST_DONE: begin
                    ad9106_reset   <= 1'b1;
                    ad9106_trigger <= 1'b0;
                    init_done      <= 1'b1;
                end

                default: begin
                    state <= ST_RESET_LOW;
                end
            endcase
        end
    end

    ad9106_spi_writer #(
        .SPI_HALF_DIV(SPI_HALF_DIV)
    ) spi_writer_i (
        .clk      (clk),
        .resetn   (resetn),
        .start    (spi_start),
        .addr     (spi_addr),
        .wdata    (spi_wdata),
        .busy     (spi_busy),
        .done     (spi_done),
        .sclk     (ad9106_sclk),
        .sdio     (ad9106_sdio),
        .cs_n     (ad9106_cs_n)
    );

    // SDO is intentionally unused because this demo only writes fixed settings.
    wire unused_sdo = ad9106_sdo;

endmodule
