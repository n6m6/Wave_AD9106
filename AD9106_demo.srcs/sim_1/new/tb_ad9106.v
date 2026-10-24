`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Testbench for the AD9106 power-on SPI initializer.
//////////////////////////////////////////////////////////////////////////////////

module tb_ad9106;

    localparam integer CLK_IN_HZ         = 50000000;
    localparam integer SYS_CLK_HZ        = 100000000;
    localparam integer SPI_CLK_HZ        = 1000000;
    localparam integer RESET_LOW_CYCLES  = 100000;
    localparam integer RESET_HIGH_CYCLES = 100000;

    localparam [14:0] REG_PAT_STATUS  = 15'h001e;
    localparam [14:0] REG_RAMUPDATE   = 15'h001d;
    localparam [14:0] REG_PAT_TIMEBASE = 15'h0028;
    localparam [14:0] REG_PAT_PERIOD  = 15'h0029;
    localparam [14:0] REG_DDS_TW32    = 15'h003e;
    localparam [14:0] REG_DDS_TW1     = 15'h003f;
    localparam [14:0] REG_WAV2_1CFG   = 15'h0027;
    localparam [14:0] REG_START_ADDR4 = 15'h0051;
    localparam [14:0] REG_STOP_ADDR4  = 15'h0052;
    localparam [14:0] REG_START_ADDR3 = 15'h0055;
    localparam [14:0] REG_STOP_ADDR3  = 15'h0056;
    localparam [14:0] REG_SRAM_BASE   = 15'h6000;

    localparam [23:0] EXPECT_DDS_WORD = 24'h113D33;
    localparam [15:0] EXPECT_TIMEBASE = 16'h0111;
    localparam [15:0] EXPECT_PERIOD   = 16'd1485;
    localparam integer EXPECT_SQUARE_WORDS = 1485;
    localparam integer EXPECT_SRAM_WORDS = 2970;
    localparam integer EXPECT_CFG_BASE   = 1 + EXPECT_SRAM_WORDS + 1;
    localparam integer EXPECT_WRITES  = 3011;

    reg clk_in = 1'b0;
    reg resetn = 1'b0;
    reg ad9106_sdo = 1'b0;

    wire ad9106_sclk;
    wire ad9106_sdio;
    wire ad9106_cs_n;
    wire ad9106_reset;
    wire ad9106_trigger;
    wire ad9106_clken;
    wire init_done;
    wire init_busy;
    wire clk_100m;
    wire clk_wiz_locked;

    reg [31:0] spi_shift = 32'h00000000;
    reg [31:0] spi_word = 32'h00000000;
    reg [5:0]  spi_bits = 6'd0;
    reg [14:0] wr_addr [0:3015];
    reg [15:0] wr_data [0:3015];
    reg [14:0] exp_sram_addr;
    integer wr_count = 0;
    integer i;
    integer square_rising_edges;
    reg [15:0] expected_square;
    realtime t0;
    realtime t1;
    realtime t2;
    realtime t3;
    realtime t4;
    realtime avg_period;

    design_1_wrapper dut (
        .clk_in           (clk_in),
        .resetn           (resetn),
        .uart_rx_0        (1'b1),
        .uart_tx_0        (),
        .ad9106_sclk_0    (ad9106_sclk),
        .ad9106_sdio_0    (ad9106_sdio),
        .ad9106_sdo_0     (ad9106_sdo),
        .ad9106_cs_n_0    (ad9106_cs_n),
        .ad9106_reset_0   (ad9106_reset),
        .ad9106_trigger_0 (ad9106_trigger),
        .ad9106_clken_0   (ad9106_clken),
        .init_done_0      (init_done),
        .init_busy_0      (init_busy)
    );

    assign clk_100m = dut.design_1_i.clk_wiz_clk_out1;
    assign clk_wiz_locked = dut.design_1_i.clk_wiz_locked;

    always #10 clk_in = ~clk_in;

    always @(posedge ad9106_cs_n) begin
        spi_bits <= 6'd0;
        spi_shift <= 32'h00000000;
    end

    always @(posedge ad9106_sclk) begin
        if (!ad9106_cs_n) begin
            spi_shift <= {spi_shift[30:0], ad9106_sdio};
            if (spi_bits == 6'd31) begin
                spi_word = {spi_shift[30:0], ad9106_sdio};
                wr_addr[wr_count] <= spi_word[30:16];
                wr_data[wr_count] <= spi_word[15:0];
                wr_count <= wr_count + 1;
                spi_bits <= 6'd0;
            end else begin
                spi_bits <= spi_bits + 6'd1;
            end
        end
    end

    task fail;
        input [8*96-1:0] msg;
        begin
            $display("FAIL: %0s", msg);
            $finish;
        end
    endtask

    task check_write;
        input integer index;
        input [14:0] exp_addr;
        input [15:0] exp_data;
        begin
            if (wr_addr[index] !== exp_addr) begin
                $display("FAIL: write[%0d] addr expected 0x%04h got 0x%04h",
                         index, exp_addr, wr_addr[index]);
                $finish;
            end

            if (wr_data[index] !== exp_data) begin
                $display("FAIL: write[%0d] data expected 0x%04h got 0x%04h",
                         index, exp_data, wr_data[index]);
                $finish;
            end
        end
    endtask

    task check_period_range;
        input [8*32-1:0] name;
        input realtime period_ns;
        input realtime min_ns;
        input realtime max_ns;
        begin
            if ((period_ns < min_ns) || (period_ns > max_ns)) begin
                $display("FAIL: %0s period expected %.3f..%.3f ns, got %.3f ns",
                         name, min_ns, max_ns, period_ns);
                $finish;
            end
        end
    endtask

    initial begin : clock_checks
        @(posedge clk_in);
        t0 = $realtime;
        @(posedge clk_in);
        t1 = $realtime;
        check_period_range("clk_in", t1 - t0, 19.8, 20.2);

        wait (resetn === 1'b1);
        wait (clk_wiz_locked === 1'b1);
        repeat (8) @(posedge clk_100m);
        t0 = $realtime;
        @(posedge clk_100m);
        t1 = $realtime;
        @(posedge clk_100m);
        t2 = $realtime;
        @(posedge clk_100m);
        t3 = $realtime;
        @(posedge clk_100m);
        t4 = $realtime;
        avg_period = (t4 - t0) / 4.0;
        check_period_range("clk_wiz clk_out1", avg_period, 9.8, 10.2);
        $display("INFO: clk_wiz locked; 50 MHz input converted to %.3f MHz output",
                 1000.0 / avg_period);
    end

    initial begin : timeout_watchdog
        repeat (4) @(posedge clk_in);
        resetn = 1'b1;

        repeat (6000000) begin
            @(posedge clk_in);
            if (init_done)
                disable timeout_watchdog;
        end

        fail("timeout waiting for init_done");
    end

    initial begin : wait_done
        wait (init_done === 1'b1);
        wait (ad9106_cs_n === 1'b1);
        repeat (20) @(posedge clk_100m);

        if (init_busy !== 1'b0)
            fail("init_busy did not deassert");
        if (ad9106_reset !== 1'b1)
            fail("ad9106_reset is not released");
        if (ad9106_trigger !== 1'b0)
            fail("ad9106_trigger did not go low");
        if (ad9106_clken !== 1'b1)
            fail("ad9106_clken is not enabled");

        if (wr_count != EXPECT_WRITES) begin
            $display("FAIL: expected %0d SPI writes, got %0d", EXPECT_WRITES, wr_count);
            $finish;
        end

        check_write(0, REG_PAT_STATUS, 16'h0004);

        for (i = 0; i < EXPECT_SRAM_WORDS; i = i + 1) begin
            exp_sram_addr = REG_SRAM_BASE + i;
            if (wr_addr[1 + i] !== exp_sram_addr) begin
                $display("FAIL: SRAM write[%0d] addr expected 0x%04h got 0x%04h",
                         i, exp_sram_addr, wr_addr[1 + i]);
                $display("TRACE: wr[0]=0x%04h/0x%04h wr[1]=0x%04h/0x%04h wr[2]=0x%04h/0x%04h",
                         wr_addr[0], wr_data[0], wr_addr[1], wr_data[1], wr_addr[2], wr_data[2]);
                $finish;
            end
        end

        square_rising_edges = 0;
        for (i = 0; i < EXPECT_SQUARE_WORDS; i = i + 1) begin
            expected_square = (((i * 50) % 1485) < 743) ? 16'h4000 : 16'hc000;
            if (wr_data[1 + i] !== expected_square) begin
                $display("FAIL: square sample[%0d] expected 0x%04h got 0x%04h",
                         i, expected_square, wr_data[1 + i]);
                $finish;
            end
            if (i > 0 && wr_data[1 + i] == 16'h4000 &&
                wr_data[i] == 16'hc000)
                square_rising_edges = square_rising_edges + 1;
        end
        if (wr_data[1] == 16'h4000 &&
            wr_data[EXPECT_SQUARE_WORDS] == 16'hc000)
            square_rising_edges = square_rising_edges + 1;
        if (square_rising_edges != 50)
            fail("square waveform must have 50 cycles per 1485 DAC clocks");

        check_write(1 + 1485, REG_SRAM_BASE + 15'd1485, 16'h0000);
        check_write(1 + 1486, REG_SRAM_BASE + 15'd1486, 16'h0000);
        check_write(1 + 1487, REG_SRAM_BASE + 15'd1487, 16'h0000);
        check_write(1 + 1488, REG_SRAM_BASE + 15'd1488, 16'h02a0);
        check_write(1 + 1782, REG_SRAM_BASE + 15'd1782, 16'h0000);
        check_write(1 + 2969, REG_SRAM_BASE + 15'd2969, 16'h0000);

        check_write(1 + EXPECT_SRAM_WORDS, REG_PAT_STATUS, 16'h0000);
        check_write(EXPECT_CFG_BASE + 5,  REG_PAT_TIMEBASE, EXPECT_TIMEBASE);
        check_write(EXPECT_CFG_BASE + 6,  REG_PAT_PERIOD, EXPECT_PERIOD);
        check_write(EXPECT_CFG_BASE + 19, REG_DDS_TW32, EXPECT_DDS_WORD[23:8]);
        check_write(EXPECT_CFG_BASE + 20, REG_DDS_TW1,  {EXPECT_DDS_WORD[7:0], 8'h00});
        check_write(EXPECT_CFG_BASE + 28, REG_WAV2_1CFG, 16'h1131);
        check_write(EXPECT_CFG_BASE + 30, REG_START_ADDR4, 16'h5cd0);
        check_write(EXPECT_CFG_BASE + 31, REG_STOP_ADDR4,  16'hb990);
        check_write(EXPECT_CFG_BASE + 33, REG_START_ADDR3, 16'h0000);
        check_write(EXPECT_CFG_BASE + 34, REG_STOP_ADDR3,  16'h5cc0);
        check_write(EXPECT_WRITES - 2, REG_PAT_STATUS, 16'h0001);
        check_write(EXPECT_WRITES - 1, REG_RAMUPDATE, 16'h0001);

        $display("PASS: AD9106 init completed with %0d SPI writes", wr_count);
        $finish;
    end

endmodule
