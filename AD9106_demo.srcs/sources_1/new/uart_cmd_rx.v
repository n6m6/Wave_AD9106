`timescale 1ns / 1ps
// UART 8N1 receiver. data_valid and frame_error are one-clock pulses.
module uart_cmd_rx #(
    parameter integer SYS_CLK_HZ = 100000000,
    parameter integer BAUD_RATE  = 115200
) (
    input wire clk,
    input wire resetn,
    input wire uart_rx,
    output reg [7:0] data,
    output reg data_valid,
    output reg frame_error
);
    localparam integer DIV = (SYS_CLK_HZ + BAUD_RATE/2) / BAUD_RATE;
    localparam [2:0] IDLE=0, START=1, DATA=2, STOP=3, RECOVER=4;
    (* ASYNC_REG = "TRUE" *) reg rx_meta, rx_sync;
    reg [2:0] state, bit_index;
    reg [31:0] count;
    reg [7:0] shift;

    always @(posedge clk) begin
        if (!resetn) begin
            rx_meta <= 1'b1;
            rx_sync <= 1'b1;
        end else begin
            rx_meta <= uart_rx;
            rx_sync <= rx_meta;
        end
    end

    always @(posedge clk) begin
        if (!resetn) begin
            state <= IDLE;
            bit_index <= 0;
            count <= 0;
            shift <= 0;
            data <= 0;
            data_valid <= 0;
            frame_error <= 0;
        end else begin
            data_valid <= 0;
            frame_error <= 0;
            case (state)
                IDLE: if (!rx_sync) begin
                    count <= DIV/2 - 1;
                    state <= START;
                end
                START: if (count != 0) count <= count - 1;
                    else if (rx_sync) state <= IDLE; // Reject a short glitch.
                    else begin
                        count <= DIV - 1;
                        bit_index <= 0;
                        state <= DATA;
                    end
                DATA: if (count != 0) count <= count - 1;
                    else begin
                        shift[bit_index] <= rx_sync;
                        count <= DIV - 1;
                        if (bit_index == 7) state <= STOP;
                        else bit_index <= bit_index + 1'b1;
                    end
                STOP: if (count != 0) count <= count - 1;
                    else if (rx_sync) begin
                        data <= shift;
                        data_valid <= 1;
                        state <= IDLE;
                    end else begin
                        frame_error <= 1;
                        count <= 0;
                        state <= RECOVER;
                    end
                // A break produces one error; require a whole idle bit to rearm.
                RECOVER: if (!rx_sync) count <= 0;
                    else if (count == DIV-1) begin
                        count <= 0;
                        state <= IDLE;
                    end else count <= count + 1'b1;
                default: state <= IDLE;
            endcase
        end
    end
endmodule
