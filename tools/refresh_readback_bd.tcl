set task_root [file dirname [file dirname [file normalize [info script]]]]
open_project [file join $task_root AD9106_demo.xpr]
open_bd_design [file join $task_root AD9106_demo.srcs sources_1 bd design_1 design_1.bd]
update_ip_catalog -update_module_ref
foreach cell {AD9106_0 ad9106_cmd_parser_0 uart_cmd_tx_0} {
    update_module_reference [get_ips design_1_${cell}_0]
}
foreach {src dst} {
    AD9106_0/cfg_rdata ad9106_cmd_parser_0/cfg_rdata
    ad9106_cmd_parser_0/rsp_data uart_cmd_tx_0/rsp_data
} {
    if {[llength [get_bd_nets -quiet -of_objects [get_bd_pins $dst]]] == 0} {
        connect_bd_net [get_bd_pins $src] [get_bd_pins $dst]
    }
}
validate_bd_design
save_bd_design
generate_target all [get_files design_1.bd]
close_project
