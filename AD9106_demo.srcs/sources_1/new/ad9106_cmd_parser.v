`timescale 1ns / 1ps
// Fixed 24-byte request; see docs/UART_CONTROL.md for the wire protocol.
// Generates individual writes, waiting for cfg_done after EACH acceptance.
// One outstanding PC command. Do not send another until its reply is received.
module ad9106_cmd_parser #(
    parameter integer SYS_CLK_HZ = 100000000,
    parameter integer FRAME_TIMEOUT_CYCLES = SYS_CLK_HZ / 10
) (
    input wire clk,
    input wire resetn,
    input wire [7:0] rx_data,
    input wire rx_valid,
    input wire rx_error,
    input wire init_done,
    output reg cfg_valid,
    input wire cfg_ready,
    output reg [14:0] cfg_addr,
    output reg [15:0] cfg_wdata,
    output reg cfg_last,
    input wire cfg_done,
    input wire [15:0] cfg_rdata,
    output wire rsp_valid,
    input wire rsp_ready,
    output reg [7:0] rsp_seq,
    output reg [7:0] rsp_cmd,
    output reg [7:0] rsp_status,
    output reg [15:0] rsp_data,
    input wire rsp_done,
    output wire busy
);
    localparam [2:0] RECEIVE=0, CHECK=1, ISSUE=2, WAIT_WRITE=3,
                     RESPONSE=4, WAIT_RESPONSE=5;
    reg [2:0] state;
    reg [4:0] pos;
    reg [7:0] frame [0:21];
    reg [7:0] checksum, received_checksum;
    reg [31:0] timeout_count;
    reg [10:0] write_index, square_phase;
    // Scene mode reuses cfg_* without adding BD ports. Legacy presets are
    // blocked after entering it because their fixed SRAM map is no longer valid.
    reg scene_mode, scene_session, scene_mem_access, scene_committed;
    reg scene_payload_ok;
    integer check_index;
    integer i;

    wire [23:0] rate_word = {frame[9], frame[10], frame[11]};
    wire [15:0] gain = {frame[5], frame[6]};
    wire [15:0] offset = {frame[7], frame[8]};
    wire [15:0] phase_word = {frame[12], frame[13]};
    wire [15:0] duty = {frame[14], frame[15]};
    wire [15:0] square_high = {frame[16], frame[17]};
    wire [15:0] square_low = {frame[18], frame[19]};
    wire [15:0] block_addr = {frame[4], frame[5]};
    wire [7:0] block_count = frame[6];
    wire enabled = frame[4][0];
    wire [15:0] packed_gain = enabled ? {gain[11:0], 4'd0} : 16'd0;
    wire [15:0] packed_offset = enabled ? {offset[11:0], 4'd0} : 16'd0;
    wire [11:0] phase_sum = {1'b0, square_phase} + {1'b0, rate_word[10:0]};
    wire [11:0] phase_next = (phase_sum >= 1485) ? phase_sum - 12'd1485 : phase_sum;
    wire common_ok = frame[4] <= 1 && gain[15:12] == 0 &&
                     offset[15:12] == 0 && frame[20] == 0 && frame[21] == 0;
    wire sine_ok = rate_word >= 1 && rate_word <= 24'h7fffff &&
                   duty == 0 && square_high == 0 && square_low == 0;
    wire triangle_ok = rate_word >= 1 && rate_word <= 63 && phase_word == 0 &&
                       duty == 0 && square_high == 0 && square_low == 0;
    // Each high/low interval must contain at least one DAC sample.
    wire square_ok = rate_word >= 1 && rate_word <= 742 && phase_word == 0 &&
                     duty >= rate_word && duty <= 24'd1485-rate_word &&
                     square_high[15:12] == 0 && square_low[15:12] == 0;
    assign rsp_valid = state == RESPONSE;
    assign busy = (state != RECEIVE) || (pos != 0);

    function scene_address_ok;
        input [16:0] address;
        begin
            scene_address_ok = 0;
            if (address >= 17'h06000 && address <= 17'h06fff)
                scene_address_ok = 1;
            else if (address == 17'h07100 || address == 17'h07101 ||
                     (address >= 17'h07200 && address < 17'h07480))
                scene_address_ok = 1;
            else case (address)
                17'h1e,17'h1f,17'h20,
                17'h22,17'h23,17'h24,17'h25,17'h26,17'h27,17'h28,17'h29,
                17'h2a,17'h2b,17'h2e,17'h2f,17'h30,17'h31,
                17'h32,17'h33,17'h34,17'h35,17'h36,17'h37,
                17'h3e,17'h3f,17'h40,17'h41,17'h42,17'h43,17'h44,17'h45,
                17'h50,17'h51,17'h52,17'h53,17'h54,17'h55,17'h56,17'h57,
                17'h58,17'h59,17'h5a,17'h5b,17'h5c,17'h5d,17'h5e,17'h5f:
                    scene_address_ok = 1;
                default: scene_address_ok = 0;
            endcase
        end
    endfunction

    // Validate the ENTIRE block before sending its first SPI write.
    always @(*) begin
        scene_payload_ok = 1;
        if (rsp_cmd == 8'h45) begin
            if (block_addr > 16'h0060) scene_payload_ok = 0;
            for (check_index=6; check_index<22; check_index=check_index+1)
                if (frame[check_index] != 0) scene_payload_ok = 0;
        end else if (rsp_cmd == 8'h41) begin
            if (block_count < 1 || block_count > 7 || frame[21] != 0)
                scene_payload_ok = 0;
            for (check_index=0; check_index<7; check_index=check_index+1) begin
                if (check_index < block_count) begin
                    if (!scene_address_ok({1'b0,block_addr} + check_index))
                        scene_payload_ok = 0;
                    // RUN and RAMUPDATE may only be issued by BEGIN/COMMIT/ABORT.
                    if (block_addr + check_index == 16'h001e &&
                        {frame[7+2*check_index],frame[8+2*check_index]} != 16'h0000 &&
                        {frame[7+2*check_index],frame[8+2*check_index]} != 16'h0004)
                        scene_payload_ok = 0;
                end else if (frame[7+2*check_index] != 0 || frame[8+2*check_index] != 0)
                    scene_payload_ok = 0;
            end
        end else begin
            for (check_index=4; check_index<22; check_index=check_index+1)
                if (frame[check_index] != 0) scene_payload_ok = 0;
        end
    end

    always @(*) begin
        cfg_valid = state == ISSUE;
        cfg_addr = 15'h001e;
        cfg_wdata = 16'h0000;
        cfg_last = 0;
        case (rsp_cmd)
            8'h45: begin // Read-only diagnostic; no RUN/trigger mutation.
                cfg_addr=15'h7000+block_addr[6:0]; cfg_wdata=0;
            end
            8'h40: begin // BEGIN: stop AND mute continuous DC before SRAM access.
                if (write_index == 0) begin cfg_addr=15'h001e; cfg_wdata=0; end
                else if (write_index <= 4) begin cfg_addr=15'h0032+write_index-1; cfg_wdata=0; end
                else if (write_index <= 8) begin cfg_addr=15'h0022+write_index-5; cfg_wdata=0; end
                else begin cfg_addr=15'h001d; cfg_wdata=1; end
            end
            8'h41: begin // WRITE: 1..7 consecutive 16-bit register/SRAM words.
                cfg_addr=block_addr[14:0]+write_index;
                cfg_wdata={frame[7+2*write_index],frame[8+2*write_index]};
            end
            8'h42,8'h44: begin // Initial/repeated start: RUN -> RAMUPDATE -> trigger.
                case (write_index)
                    0: begin cfg_addr=15'h001e; cfg_wdata=16'h0001; end
                    1: begin cfg_addr=15'h001d; cfg_wdata=16'h0001; cfg_last=1; end
                    default: begin end
                endcase
            end
            8'h43: begin // ABORT also mutes continuous DC sources and offsets.
                if (write_index <= 3) begin cfg_addr=15'h0032+write_index; cfg_wdata=0; end
                else if (write_index <= 7) begin cfg_addr=15'h0022+write_index-4; cfg_wdata=0; end
                else if (write_index <= 11) begin cfg_addr=15'h002e+write_index-8; cfg_wdata=0; end
                else begin cfg_addr=15'h001d; cfg_wdata=1; end // Keep TRIGGER high; no RUN clear.
            end
            8'h01: begin // DAC1 sine: 8 SPI writes.
                case (write_index)
                    0: begin cfg_addr=15'h001e; cfg_wdata=16'h0000; end
                    1: begin cfg_addr=15'h0035; cfg_wdata=packed_gain; end
                    2: begin cfg_addr=15'h0025; cfg_wdata=packed_offset; end
                    3: begin cfg_addr=15'h003e; cfg_wdata=rate_word[23:8]; end
                    4: begin cfg_addr=15'h003f; cfg_wdata={rate_word[7:0],8'd0}; end
                    5: begin cfg_addr=15'h0043; cfg_wdata=phase_word; end
                    6: begin cfg_addr=15'h001e; cfg_wdata=16'h0001; end
                    7: begin cfg_addr=15'h001d; cfg_wdata=16'h0001; cfg_last=1; end
                    default: begin end
                endcase
            end
            8'h02: begin // DAC2 triangle: 6 SPI writes.
                case (write_index)
                    0: begin cfg_addr=15'h001e; cfg_wdata=16'h0000; end
                    1: begin cfg_addr=15'h0034; cfg_wdata=packed_gain; end
                    2: begin cfg_addr=15'h0024; cfg_wdata=packed_offset; end
                    3: begin
                        cfg_addr=15'h0037;
                        cfg_wdata={frame[11][5:0],2'b10,6'd1,2'b11};
                    end
                    4: begin cfg_addr=15'h001e; cfg_wdata=16'h0001; end
                    5: begin cfg_addr=15'h001d; cfg_wdata=16'h0001; cfg_last=1; end
                    default: begin end
                endcase
            end
            8'h03: begin // DAC3 square: rewrite only SRAM 0x000..0x5cc.
                if (write_index >= 2 && write_index <= 1486) begin
                    cfg_addr = 15'h6000 + {4'd0, write_index} - 15'd2;
                    cfg_wdata = (square_phase < duty) ?
                                {square_high[11:0],4'd0} : {square_low[11:0],4'd0};
                end else begin
                    case (write_index)
                        0: begin cfg_addr=15'h001e; cfg_wdata=16'h0000; end
                        1: begin cfg_addr=15'h001e; cfg_wdata=16'h0004; end
                        1487: begin cfg_addr=15'h001e; cfg_wdata=16'h0000; end
                        1488: begin cfg_addr=15'h0033; cfg_wdata=packed_gain; end
                        1489: begin cfg_addr=15'h0023; cfg_wdata=packed_offset; end
                        1490: begin cfg_addr=15'h001e; cfg_wdata=16'h0001; end
                        1491: begin cfg_addr=15'h001d; cfg_wdata=16'h0001; cfg_last=1; end
                        default: begin end
                    endcase
                end
            end
            default: begin end
        endcase
    end

    always @(posedge clk) begin
        if (!resetn) begin
            state <= RECEIVE;
            pos <= 0;
            checksum <= 0;
            received_checksum <= 0;
            timeout_count <= 0;
            write_index <= 0;
            square_phase <= 0;
            scene_mode <= 0;
            scene_session <= 0;
            scene_mem_access <= 0;
            scene_committed <= 0;
            rsp_seq <= 0;
            rsp_cmd <= 0;
            rsp_status <= 0;
            rsp_data <= 0;
            for (i=0; i<22; i=i+1) frame[i] <= 0;
        end else begin
            case (state)
                RECEIVE: begin
                    if (pos == 0 || rx_valid) timeout_count <= 0;
                    else timeout_count <= timeout_count + 1'b1;
                    if (rx_error && pos != 0) begin
                        rsp_status <= 8'h06;
                        pos <= 0;
                        state <= RESPONSE;
                    end else if (rx_valid) begin
                        if (pos == 0) begin
                            if (rx_data == 8'haa) begin
                                pos <= 1;
                                rsp_seq <= 0;
                                rsp_cmd <= 0;
                                checksum <= 0;
                            end
                        end else if (pos == 1) begin
                            if (rx_data == 8'h55) pos <= 2;
                            else if (rx_data != 8'haa) pos <= 0;
                        end else if (pos <= 21) begin
                            frame[pos] <= rx_data;
                            checksum <= checksum ^ rx_data;
                            if (pos == 2) rsp_seq <= rx_data;
                            if (pos == 3) rsp_cmd <= rx_data;
                            pos <= pos + 1'b1;
                        end else if (pos == 22) begin
                            received_checksum <= rx_data;
                            pos <= 23;
                        end else begin
                            pos <= 0;
                            if (rx_data != 8'h0d) begin
                                rsp_status <= 8'h01;
                                state <= RESPONSE;
                            end else if (received_checksum != checksum) begin
                                rsp_status <= 8'h02;
                                state <= RESPONSE;
                            end else state <= CHECK;
                        end
                    end else if (pos != 0 && timeout_count >= FRAME_TIMEOUT_CYCLES-1) begin
                        pos <= 0;
                        rsp_status <= 8'h05;
                        state <= RESPONSE;
                    end
                end
                CHECK: begin
                    rsp_data <= 0;
                    if (rsp_cmd == 8'h45) begin
                        if (!scene_payload_ok) begin rsp_status<=4; state<=RESPONSE; end
                        else if (!init_done) begin rsp_status<=7; state<=RESPONSE; end
                        else begin rsp_status<=0; write_index<=0; state<=ISSUE; end
                    end else if (rsp_cmd >= 8'h40 && rsp_cmd <= 8'h44) begin
                        if (!scene_payload_ok) begin
                            rsp_status <= 8'h04;
                            state <= RESPONSE;
                        end else if (!init_done) begin
                            rsp_status <= 8'h07;
                            state <= RESPONSE;
                        end else if ((rsp_cmd == 8'h40 && scene_session) ||
                                     ((rsp_cmd == 8'h41 || rsp_cmd == 8'h42) && !scene_session) ||
                                     (rsp_cmd == 8'h43 && !scene_session && !scene_mode) ||
                                     (rsp_cmd == 8'h44 && (!scene_committed || scene_session)) ||
                                     (rsp_cmd == 8'h42 && scene_mem_access) ||
                                     (rsp_cmd == 8'h41 && block_addr >= 16'h6000 &&
                                      block_addr <= 16'h6fff && !scene_mem_access)) begin
                            rsp_status <= 8'h08;
                            state <= RESPONSE;
                        end else begin
                            if (rsp_cmd == 8'h40) begin
                                scene_mode <= 1;
                                scene_session <= 1;
                                scene_mem_access <= 0;
                                scene_committed <= 0;
                            end
                            rsp_status <= 0;
                            write_index <= 0;
                            state <= ISSUE;
                        end
                    end else if (rsp_cmd < 1 || rsp_cmd > 3) begin
                        rsp_status <= 8'h03;
                        state <= RESPONSE;
                    end else if (scene_mode) begin
                        rsp_status <= 8'h08;
                        state <= RESPONSE;
                    end else if (!common_ok ||
                        (rsp_cmd == 1 && !sine_ok) ||
                        (rsp_cmd == 2 && !triangle_ok) ||
                        (rsp_cmd == 3 && !square_ok)) begin
                        rsp_status <= 8'h04;
                        state <= RESPONSE;
                    end else if (!init_done) begin
                        rsp_status <= 8'h07;
                        state <= RESPONSE;
                    end else begin
                        rsp_status <= 0;
                        write_index <= 0;
                        square_phase <= 0;
                        state <= ISSUE;
                    end
                end
                ISSUE: if (cfg_ready) state <= WAIT_WRITE;
                WAIT_WRITE: if (cfg_done) begin
                    if (rsp_cmd == 8'h41 && cfg_addr == 15'h001e)
                        scene_mem_access <= (cfg_wdata == 16'h0004);
                    if (rsp_cmd == 8'h43) scene_mem_access <= 0;
                    if (rsp_cmd == 8'h45) begin
                        rsp_data <= cfg_rdata;
                        state <= RESPONSE;
                    end else if ((rsp_cmd == 8'h40 && write_index == 9) || (rsp_cmd == 8'h41 && write_index == block_count-1))
                        state <= RESPONSE;
                    else if (cfg_last || (rsp_cmd == 8'h43 && write_index == 12)) begin
                        if (rsp_cmd == 8'h42 || rsp_cmd == 8'h43) scene_session <= 0;
                        if (rsp_cmd == 8'h42) scene_committed <= 1;
                        if (rsp_cmd == 8'h43) scene_committed <= 0;
                        state <= RESPONSE;
                    end
                    else begin
                        if (rsp_cmd == 3 && write_index >= 2 && write_index <= 1486)
                            square_phase <= phase_next[10:0];
                        write_index <= write_index + 1'b1;
                        state <= ISSUE;
                    end
                end
                RESPONSE: if (rsp_ready) state <= WAIT_RESPONSE;
                WAIT_RESPONSE: if (rsp_done) begin
                    timeout_count <= 0;
                    state <= RECEIVE;
                end
                default: state <= RECEIVE;
            endcase
        end
    end
endmodule
