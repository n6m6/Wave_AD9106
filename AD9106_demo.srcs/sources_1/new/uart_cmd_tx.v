`timescale 1ns / 1ps
// Response packet: 55 AA SEQ CMD STATUS (SEQ ^ CMD ^ STATUS) 0D 0A.
// Capture a response only on rsp_valid && rsp_ready.
module uart_cmd_tx #(
    parameter integer SYS_CLK_HZ = 100000000,
    parameter integer BAUD_RATE  = 115200
) (
    input wire clk,
    input wire resetn,
    input wire rsp_valid,
    output wire rsp_ready,
    input wire [7:0] rsp_seq,
    input wire [7:0] rsp_cmd,
    input wire [7:0] rsp_status,
    input wire [15:0] rsp_data,
    output reg uart_tx,
    output reg busy,
    output reg done
);
    localparam integer DIV = (SYS_CLK_HZ + BAUD_RATE/2) / BAUD_RATE;
    reg [79:0] packet;
    reg [3:0] byte_index;
    reg [3:0] last_byte;
    reg [3:0] bit_index;
    reg [31:0] count;
    assign rsp_ready = !busy;

    always @(posedge clk) begin
        if (!resetn) begin
            uart_tx <= 1;
            busy <= 0;
            done <= 0;
            packet <= 0;
            byte_index <= 0;
            last_byte <= 7;
            bit_index <= 0;
            count <= 0;
        end else begin
            done <= 0;
            if (!busy) begin
                uart_tx <= 1;
                if (rsp_valid) begin
                    if (rsp_cmd == 8'h45) begin
                        packet <= {8'h0a,8'h0d,rsp_seq ^ rsp_cmd ^ rsp_status ^ rsp_data[15:8] ^ rsp_data[7:0],
                                   rsp_data[7:0],rsp_data[15:8],rsp_status,rsp_cmd,rsp_seq,8'haa,8'h55};
                        last_byte <= 9;
                    end else begin
                        packet <= {16'd0,8'h0a,8'h0d,rsp_seq ^ rsp_cmd ^ rsp_status,
                                   rsp_status,rsp_cmd,rsp_seq,8'haa,8'h55};
                        last_byte <= 7;
                    end
                    byte_index <= 0;
                    bit_index <= 0;
                    count <= DIV-1;
                    uart_tx <= 0; // Start bit.
                    busy <= 1;
                end
            end else if (count != 0) count <= count - 1;
            else begin
                count <= DIV-1;
                if (bit_index < 8) begin
                    uart_tx <= packet[bit_index];
                    bit_index <= bit_index + 1'b1;
                end else if (bit_index == 8) begin
                    uart_tx <= 1; // Stop bit lasts a whole DIV clocks.
                    bit_index <= 9;
                end else if (byte_index == last_byte) begin
                    busy <= 0;
                    done <= 1;
                end else begin
                    packet <= {8'd0, packet[79:8]};
                    byte_index <= byte_index + 1'b1;
                    bit_index <= 0;
                    uart_tx <= 0;
                end
            end
        end
    end
endmodule
