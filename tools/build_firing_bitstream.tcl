set project_root [file dirname [file dirname [file normalize [info script]]]]
open_project [file join $project_root AD9106_demo.xpr]
config_ip_cache -disable_cache
update_compile_order -fileset sources_1
# Refreshing module references can remove their old synthesis runs.
create_ip_run [get_files design_1.bd]
# Block Design module references are synthesized out of context. Resetting
# only synth_1 silently reuses old IP checkpoints and produces a stale bitfile.
foreach ip_run {design_1_AD9106_0_0_synth_1 design_1_ad9106_cmd_parser_0_0_synth_1 design_1_uart_cmd_tx_0_0_synth_1} {
    reset_run $ip_run
    launch_runs $ip_run -jobs 4
    wait_on_run $ip_run
    if {[get_property STATUS [get_runs $ip_run]] ne "synth_design Complete!"} {
        error "IP synthesis failed: ${ip_run}: [get_property STATUS [get_runs $ip_run]]"
    }
}
reset_run synth_1
launch_runs synth_1 -jobs 4
wait_on_run synth_1
if {[get_property STATUS [get_runs synth_1]] ne "synth_design Complete!"} {
    error "Synthesis failed: [get_property STATUS [get_runs synth_1]]"
}
reset_run impl_1
launch_runs impl_1 -to_step write_bitstream -jobs 4
wait_on_run impl_1
if {[get_property STATUS [get_runs impl_1]] ne "write_bitstream Complete!"} {
    error "Bitstream generation failed: [get_property STATUS [get_runs impl_1]]"
}
puts "FIRING_BITSTREAM_READY [file join $project_root AD9106_demo.runs impl_1 design_1_wrapper.bit]"
close_project
