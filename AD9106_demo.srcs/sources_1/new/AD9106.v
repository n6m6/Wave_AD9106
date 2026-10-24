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
//   DAC3/OUT3: 5 MHz square wave from SRAM addresses 0x000..0x5cc
//   DAC4/OUT4: arbitrary waveform from SRAM addresses 0x5cd..0xb99
// After init_done, the cfg_* port accepts runtime writes from the UART parser.
//////////////////////////////////////////////////////////////////////////////////

module AD9106 #(
    parameter integer SYS_CLK_HZ        = 100000000,
    parameter integer SPI_CLK_HZ        = 1000000,
    parameter integer RESET_LOW_CYCLES  = 100000,
    parameter integer RESET_HIGH_CYCLES = 100000,

    // DDS tuning word = round(fout / fclk_dac * 2^24). Default is 10 MHz
    // with the board 148.5 MHz AD9106 DAC clock oscillator.
    parameter [23:0] DDS_TUNING_WORD = 24'h113D33,

    // Digital gain is signed 12-bit fixed point in AD9106 format.
    // 12'h400 = +1.0, 12'h7ff is almost +2.0, 12'hc00 = -1.0.
    parameter [11:0] DAC1_DIG_GAIN = 12'h400,
    parameter [11:0] DAC2_DIG_GAIN = 12'h400,
    parameter [11:0] DAC3_DIG_GAIN = 12'h400,
    parameter [11:0] DAC4_DIG_GAIN = 12'h400,

    // 1485 DAC clocks per pattern give 100 kHz frequency steps at 148.5 MHz.
    // DAC3 contains 50 square cycles; DAC4 contains five original 297-point
    // arbitrary periods, preserving its 500 kHz waveform.
    parameter [3:0]  SRAM_HOLD          = 4'd1,
    parameter [3:0]  PAT_PERIOD_BASE    = 4'd1,
    parameter [15:0] PATTERN_PERIOD     = 16'd1485,

    // DAC2 triangle. ftri = fclk_dac / (2 * 16384 * TRI_SAW_STEP).
    parameter [5:0]  TRI_SAW_STEP       = 6'd4,

    // DAC3 square waveform samples, signed 12-bit AD9106 data.
    parameter [11:0] SQUARE_HIGH        = 12'h400,
    parameter [11:0] SQUARE_LOW         = 12'hc00,

    parameter integer RUNTIME_UPDATE_CYCLES =
        (SYS_CLK_HZ >= 1000000) ? SYS_CLK_HZ / 1000000 : 1
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
    output wire init_busy,

    // Runtime write port, same clk/resetn as this controller. Keep payload
    // stable until cfg_valid && cfg_ready; then wait for cfg_done.
    // Mark only the final RAMUPDATE write with cfg_last. The trigger remains
    // high during a command and goes low before its final cfg_done pulse.
    input  wire        cfg_valid,
    output wire        cfg_ready,
    input  wire [14:0] cfg_addr,
    input  wire [15:0] cfg_wdata,
    input  wire        cfg_last,
    output reg         cfg_done,
    output reg [15:0]  cfg_rdata
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

    localparam [11:0] DAC3_SRAM_START = 12'h000;
    localparam [11:0] DAC3_SRAM_STOP  = 12'h5cc;
    localparam [11:0] DAC4_SRAM_START = 12'h5cd;
    localparam [11:0] DAC4_SRAM_STOP  = 12'hb99;
    localparam integer SRAM_WORDS      = 2970;
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
    localparam [3:0] ST_RUNTIME_WRITE = 4'd9;
    localparam [3:0] ST_RUNTIME_WAIT  = 4'd10;

    reg [3:0]  state;
    reg [31:0] wait_counter;
    reg [7:0]  cfg_index;
    reg [11:0] sram_index;
    reg [11:0] sram_sample;
    reg [10:0] square_phase;
    reg [6:0]  arb_index;
    reg [1:0]  arb_repeat;
    reg        issue_spi;
    reg [14:0] issue_addr;
    reg [15:0] issue_data;
    reg [30:0] cfg_current;

    wire       spi_busy;
    reg        spi_start;
    reg [14:0] spi_addr;
    reg [15:0] spi_wdata;
    wire       spi_done;
    reg        runtime_last;
    reg        pattern_run_enabled;
    reg        spi_read;
    wire [15:0] spi_rdata;
    localparam [3:0] ST_RUNTIME_READ = 4'd13;
    localparam [3:0] ST_BASIC_WRITE = 4'd11, ST_BASIC_WAIT = 4'd12;
    wire cfg_read = cfg_addr >= 15'h7000 && cfg_addr <= 15'h7060;
    wire cfg_virtual = cfg_addr == 15'h7100 || cfg_addr == 15'h7101 ||
                       (cfg_addr >= 15'h7200 && cfg_addr < 15'h7480);
    wire basic_enabled, basic_active, basic_valid, basic_ready;
    wire [14:0] basic_addr;
    wire [15:0] basic_data;
    wire basic_first, basic_final;
    reg basic_start, basic_done, basic_update, basic_first_latched, basic_final_latched;

    assign init_busy = !init_done;
    assign cfg_ready = (state == ST_DONE) && init_done &&
                       !spi_busy && !spi_start && !spi_done && !(basic_active && cfg_read);
    assign basic_ready = state == ST_DONE && !spi_busy && !spi_start && !spi_done &&
                         !(cfg_valid && cfg_ready);
    ad9106_basic_sequencer #(.COMMIT_LEAD(64*SPI_HALF_DIV+4)) basic_player (
        .clk(clk),.resetn(resetn),.config_write(cfg_valid && cfg_ready),
        .config_addr(cfg_addr),.config_data(cfg_wdata),
        .start(basic_start),.enabled(basic_enabled),.active(basic_active),
        .valid(basic_valid),.ready(basic_ready),.addr(basic_addr),.data(basic_data),
        .done(basic_done),.first_update(basic_first),.final_update(basic_final));

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

    // Advance 50 square-wave cycles over 1485 DAC clocks (5 MHz default).
    wire [10:0] square_phase_sum = square_phase + 11'd50;
    wire [10:0] next_square_phase = (square_phase_sum >= 11'd1485) ?
                                   square_phase_sum - 11'd1485 : square_phase_sum;

    function [11:0] square_sample;
        input [10:0] phase;
        begin
            square_sample = (phase < 11'd743) ? SQUARE_HIGH : SQUARE_LOW;
        end
    endfunction

    // Repeat each of 99 points three times, then repeat that 297-point period
    // five times to fill DAC4's 1485-point buffer at the original 500 kHz.
    function [11:0] next_arbitrary_sample;
        input [6:0] index;
        input [11:0] current_sample;
        begin
            if (index < 7'd25)
                next_arbitrary_sample = current_sample + 12'h02a;
            else if (index < 7'd50)
                next_arbitrary_sample = current_sample - 12'h010;
            else if (index < 7'd75)
                next_arbitrary_sample = current_sample - 12'h045;
            else if (index < 7'd98)
                next_arbitrary_sample = current_sample + 12'h02d;
            else
                next_arbitrary_sample = 12'h000;
        end
    endfunction

    function [30:0] cfg_word;
        input [7:0] index;
        begin
            case (index)
                8'd0:  cfg_word = {REG_SPICONFIG,    16'h0000}; // 4-wire, MSB first.
                8'd1:  cfg_word = {REG_POWERCONFIG,  16'h0000}; // All DACs active, internal references on.
                8'd2:  cfg_word = {REG_CLOCKCONFIG,  16'h0000};
                8'd3:  cfg_word = {REG_PAT_TYPE,     16'h0001}; // Finite pattern: two periods per trigger.
                8'd4:  cfg_word = {REG_PATTERN_DLY,  16'h000e}; // Minimum trigger-to-output delay.
                8'd5:  cfg_word = {REG_PAT_TIMEBASE, {4'h0, SRAM_HOLD, PAT_PERIOD_BASE, 4'h1}};
                8'd6:  cfg_word = {REG_PAT_PERIOD,   PATTERN_PERIOD};
                8'd7:  cfg_word = {REG_DAC4_3PATX,   16'h0101}; // Each byte = 1: two patterns on each DAC.
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
                issue_addr = REG_SRAM_BASE + {3'd0, sram_index};
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
            sram_index     <= 12'd0;
            sram_sample    <= SQUARE_HIGH;
            square_phase   <= 11'd0;
            arb_index      <= 7'd0;
            arb_repeat     <= 2'd0;
            spi_start      <= 1'b0;
            spi_addr       <= 15'h0000;
            spi_wdata      <= 16'h0000;
            ad9106_reset   <= 1'b0;
            ad9106_trigger <= 1'b1;
            ad9106_clken   <= 1'b1;
            init_done      <= 1'b0;
            cfg_done       <= 1'b0;
            runtime_last   <= 1'b0;
            basic_start <= 0; basic_done <= 0; basic_update <= 0;
            basic_first_latched <= 0; basic_final_latched <= 0;
            pattern_run_enabled <= 1'b0;
            spi_read <= 1'b0;
            cfg_rdata <= 16'd0;
        end else begin
            spi_start    <= 1'b0;
            basic_start <= 0; basic_done <= 0;
            cfg_done     <= 1'b0;
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
                            sram_index <= 12'd0;
                            sram_sample <= SQUARE_HIGH;
                            square_phase <= 11'd0;
                            arb_index <= 7'd0;
                            arb_repeat <= 2'd0;
                            state      <= ST_MEM_OFF;
                        end else begin
                            if (sram_index < DAC3_SRAM_STOP) begin
                                square_phase <= next_square_phase;
                                sram_sample <= square_sample(next_square_phase);
                            end else if (sram_index == DAC3_SRAM_STOP) begin
                                sram_sample <= 12'h000;
                            end else if (arb_repeat == 2'd2) begin
                                arb_repeat <= 2'd0;
                                if (arb_index == 7'd98) begin
                                    arb_index <= 7'd0;
                                    sram_sample <= 12'h000;
                                end else begin
                                    arb_index <= arb_index + 7'd1;
                                    sram_sample <= next_arbitrary_sample(arb_index + 7'd1,
                                                                         sram_sample);
                                end
                            end else begin
                                arb_repeat <= arb_repeat + 2'd1;
                            end
                            sram_index <= sram_index + 12'd1;
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
                    if (spi_done) begin
                        pattern_run_enabled <= 1'b1;
                        state <= ST_UPDATE;
                    end
                end

                ST_UPDATE: begin
                    if (issue_spi && !spi_busy && !spi_start && !spi_done) begin
                        spi_addr  <= issue_addr;
                        spi_wdata <= issue_data;
                        spi_start <= 1'b1;
                    end
                    if (spi_done) begin
                        // RUN is included in the update; trigger only afterward.
                        ad9106_trigger <= 1'b0;
                        init_done <= 1'b1;
                        state <= ST_DONE;
                    end
                end

                ST_DONE: begin
                    ad9106_reset   <= 1'b1;
                    init_done      <= 1'b1;
                    if (cfg_valid && cfg_ready) begin
                        if (cfg_virtual) begin
                            cfg_done <= 1'b1;
                        end else if (cfg_read) begin
                            spi_addr <= {8'd0, cfg_addr[6:0]};
                            spi_wdata <= 16'd0;
                            spi_read <= 1'b1;
                            spi_start <= 1'b1;
                            state <= ST_RUNTIME_READ;
                        end else begin
                            spi_addr <= cfg_addr;
                            spi_wdata <= cfg_wdata;
                            if (cfg_addr == REG_PAT_STATUS)
                                pattern_run_enabled <= cfg_wdata[0];
                            spi_start <= 1'b1;
                            runtime_last <= cfg_last;
                            ad9106_trigger <= 1'b1;
                            state <= ST_RUNTIME_WRITE;
                        end
                    end else if (basic_valid && basic_ready) begin
                        spi_addr <= basic_addr; spi_wdata <= basic_data;
                        spi_read <= 0; spi_start <= 1;
                        basic_update <= basic_addr == REG_RAMUPDATE;
                        basic_first_latched <= basic_first;
                        basic_final_latched <= basic_final;
                        state <= ST_BASIC_WRITE;
                    end
                end

                ST_RUNTIME_WRITE: if (spi_done) begin
                    if (runtime_last || spi_addr == REG_RAMUPDATE) begin
                        wait_counter <= 0;
                        state <= ST_RUNTIME_WAIT;
                    end else begin
                        cfg_done <= 1'b1;
                        state <= ST_DONE;
                    end
                end

                ST_RUNTIME_WAIT: begin
                    if (RUNTIME_UPDATE_CYCLES <= 1 || wait_counter >= RUNTIME_UPDATE_CYCLES - 1) begin
                        if (runtime_last) begin
                            ad9106_trigger <= basic_enabled ? 1'b1 : !pattern_run_enabled;
                            if (basic_enabled) basic_start <= 1;
                        end
                        cfg_done <= 1'b1;
                        state <= ST_DONE;
                    end else wait_counter <= wait_counter + 1'b1;
                end

                ST_RUNTIME_READ: if (spi_done) begin
                    cfg_rdata <= spi_rdata;
                    spi_read <= 1'b0;
                    cfg_done <= 1'b1;
                    state <= ST_DONE;
                end

                ST_BASIC_WRITE: if (spi_done) begin
                    if (basic_update) begin
                        if (basic_first_latched) ad9106_trigger <= 0;
                        if (basic_final_latched) ad9106_trigger <= 1;
                        wait_counter <= 0; state <= ST_BASIC_WAIT;
                    end else begin basic_done <= 1; state <= ST_DONE; end
                end
                ST_BASIC_WAIT: begin
                    if (RUNTIME_UPDATE_CYCLES <= 1 || wait_counter >= RUNTIME_UPDATE_CYCLES-1) begin
                        basic_done <= 1; state <= ST_DONE;
                    end else wait_counter <= wait_counter+1'b1;
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
        .read_en  (spi_read),
        .sdo      (ad9106_sdo),
        .rdata    (spi_rdata),
        .busy     (spi_busy),
        .done     (spi_done),
        .sclk     (ad9106_sclk),
        .sdio     (ad9106_sdio),
        .cs_n     (ad9106_cs_n)
    );


endmodule

// FPGA-timed basic-wave events. Ten 16-bit words per event:
// absolute 100 MHz tick (high, low), DAC4..1 constants, DAC4..1 gains.
// Constants/gains are staged first; RAMUPDATE is issued at the deadline.
// The final event is always forced to zero. No automatic RUN clearing.
module ad9106_basic_sequencer #(parameter integer COMMIT_LEAD=3204)(
    input wire clk, resetn, config_write,
    input wire [14:0] config_addr,
    input wire [15:0] config_data,
    input wire start,
    output reg enabled, active,
    output wire valid,
    input wire ready,
    output wire [14:0] addr,
    output wire [15:0] data,
    input wire done,
    output wire first_update, final_update
);
    reg [15:0] event_mem [0:639];
    reg [6:0] count;
    reg [5:0] event_index;
    reg [3:0] slot;
    reg inflight;
    reg [31:0] ticks;
    wire [9:0] base = event_index * 10;
    wire [31:0] deadline = {event_mem[base],event_mem[base+1]};
    wire read_command = config_addr >= 15'h7000 && config_addr <= 15'h7060;
    wire cancel = config_write && !read_command;
    assign valid = active && !inflight && !cancel &&
                   (slot < 8 || ticks + COMMIT_LEAD >= deadline);
    assign addr = slot == 8 ? 15'h001d : 15'h002e + slot;
    assign data = slot == 8 ? 16'h0001 :
                  event_index == count-1 ? 16'h0000 : event_mem[base+2+slot];
    assign first_update = event_index == 0;
    assign final_update = event_index == count-1;
    always @(posedge clk) begin
        if (!resetn) begin
            enabled<=0; active<=0; count<=0; event_index<=0;
            slot<=0; inflight<=0; ticks<=0;
        end else begin
            if (active) ticks<=ticks+1'b1;
            if (config_write) begin
                if (config_addr>=15'h7200 && config_addr<15'h7480)
                    event_mem[config_addr-15'h7200]<=config_data;
                if (config_addr==15'h7101)
                    count <= config_data>=2 && config_data<=64 ? config_data[6:0] : 0;
                if (config_addr==15'h7100)
                    enabled <= config_data==1 && count>=2 && count<=64;
                if ((config_addr==15'h001e && config_data==0) || config_addr==15'h0032)
                    enabled<=0; // BEGIN or ABORT cancels/revokes playback.
            end
            if (cancel) begin active<=0; inflight<=0; end
            else if (start && enabled) begin
                active<=1; event_index<=0; slot<=0; inflight<=0; ticks<=0;
            end else if (active) begin
                if (valid && ready) inflight<=1;
                if (inflight && done) begin
                    inflight<=0;
                    if (slot<8) slot<=slot+1'b1;
                    else begin
                        slot<=0;
                        if (final_update) active<=0;
                        else event_index<=event_index+1'b1;
                    end
                end
            end
        end
    end
endmodule
