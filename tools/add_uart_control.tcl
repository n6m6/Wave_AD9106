# Run from the Vivado Tcl console with the existing project open.
# Add modules/testbench without changing the BD or either fileset's top.
set uart_root [file dirname [file dirname [file normalize [info script]]]]
foreach uart_file {uart_cmd_rx.v ad9106_cmd_parser.v uart_cmd_tx.v} {
    set uart_path [file join $uart_root AD9106_demo.srcs sources_1 new $uart_file]
    if {[llength [get_files -quiet $uart_path]] == 0} {
        add_files -norecurse -fileset sources_1 [list $uart_path]
    }
}
foreach uart_tb_name {tb_uart_control.sv tb_top_uart.sv tb_clock_wizard.sv tb_firing_uart.sv} {
    set uart_tb [file join $uart_root AD9106_demo.srcs sim_1 new $uart_tb_name]
    if {[llength [get_files -quiet $uart_tb]] == 0} {
        add_files -norecurse -fileset sim_1 [list $uart_tb]
    }
}
# Do not add clock_wizard_functional.sv: it replaces a generated module only in
# the isolated -FunctionalClock regression, never in the Vivado project.
update_compile_order -fileset sources_1
