# Fresh synthesis of the actual generated wrapper; no old project checkpoints.
set task_root [file dirname [file dirname [file normalize [info script]]]]
set report_dir [file join $task_root .uart_sim top_synth]
file mkdir $report_dir
create_project -in_memory -part xc7a35tfgg484-2
set rtl_dir [file join $task_root AD9106_demo.srcs sources_1 new]
set bd_dir [file join $task_root AD9106_demo.gen sources_1 bd design_1]
foreach rtl_file {ad9106_spi_writer.v AD9106.v uart_cmd_rx.v ad9106_cmd_parser.v uart_cmd_tx.v} {
    read_verilog [list [file join $rtl_dir $rtl_file]]
}
foreach module_name {design_1_AD9106_0_0 design_1_ad9106_cmd_parser_0_0 design_1_uart_cmd_rx_0_0 design_1_uart_cmd_tx_0_0} {
    read_verilog [list [file join $bd_dir ip $module_name sim ${module_name}.v]]
}
foreach clk_file {design_1_clk_wiz_0_clk_wiz.v design_1_clk_wiz_0.v} {
    read_verilog [list [file join $bd_dir ip design_1_clk_wiz_0 $clk_file]]
}
read_verilog [list [file join $bd_dir synth design_1.v]]
read_verilog [list [file join $bd_dir hdl design_1_wrapper.v]]
synth_design -top design_1_wrapper -part xc7a35tfgg484-2
read_xdc [list [file join $task_root AD9106_demo.srcs constrs_1 new AD9106.xdc]]
create_clock -name clk_in -period 20.000 [get_ports clk_in]
report_utilization -hierarchical -file [file join $report_dir utilization.rpt]
report_timing_summary -file [file join $report_dir timing.rpt]
report_clocks -file [file join $report_dir clocks.rpt]
report_drc -checks [get_drc_checks {NSTD-1 UCIO-1 CFGBVS-1}] -file [file join $report_dir io_drc.rpt]
set audit_fd [open [file join $report_dir ports.txt] w]
foreach port [get_ports] {
    puts $audit_fd "$port: PACKAGE_PIN=[get_property PACKAGE_PIN $port] IOSTANDARD=[get_property IOSTANDARD $port]"
}
close $audit_fd
write_checkpoint -force [file join $report_dir design_1_wrapper.dcp]
puts "PASS: fresh top-level synthesis completed; inspect io_drc.rpt separately"
