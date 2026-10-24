set uart_root [file dirname [file dirname [file normalize [info script]]]]
file mkdir [file join $uart_root .uart_sim]
create_project -in_memory -part xc7a35tfgg484-2
foreach uart_file {ad9106_spi_writer.v AD9106.v uart_cmd_rx.v ad9106_cmd_parser.v uart_cmd_tx.v} {
    read_verilog [list [file join $uart_root AD9106_demo.srcs sources_1 new $uart_file]]
}
foreach uart_top {uart_cmd_rx ad9106_cmd_parser uart_cmd_tx AD9106} {
    synth_design -top $uart_top -part xc7a35tfgg484-2 -mode out_of_context
    create_clock -name sys_clk -period 10.0 [get_ports clk]
    report_utilization -file [file join $uart_root .uart_sim ${uart_top}_utilization.rpt]
    report_timing_summary -file [file join $uart_root .uart_sim ${uart_top}_timing.rpt]
    close_design
}
puts "PASS: all UART control modules synthesized"
