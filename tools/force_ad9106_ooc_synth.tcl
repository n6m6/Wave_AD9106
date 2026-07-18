create_project -in_memory -part xc7a35tfgg484-2
set_property target_language Verilog [current_project]
set_property default_lib xil_defaultlib [current_project]

read_verilog -library xil_defaultlib {
  {E:/vivado project/AD9106_demo/AD9106_demo.srcs/sources_1/new/ad9106_spi_writer.v}
  {E:/vivado project/AD9106_demo/AD9106_demo.srcs/sources_1/new/AD9106.v}
  {E:/vivado project/AD9106_demo/AD9106_demo.gen/sources_1/bd/design_1/ip/design_1_AD9106_0_0/synth/design_1_AD9106_0_0.v}
}

synth_design -top design_1_AD9106_0_0 -part xc7a35tfgg484-2 -incremental_mode off -mode out_of_context
write_checkpoint -force -noxdef {E:/vivado project/AD9106_demo/AD9106_demo.gen/sources_1/bd/design_1/ip/design_1_AD9106_0_0/design_1_AD9106_0_0.dcp}
write_checkpoint -force -noxdef {E:/vivado project/AD9106_demo/AD9106_demo.runs/design_1_AD9106_0_0_synth_1/design_1_AD9106_0_0.dcp}
report_utilization -file {E:/vivado project/AD9106_demo/AD9106_demo.runs/design_1_AD9106_0_0_synth_1/design_1_AD9106_0_0_utilization_synth.rpt}
