param([switch]$Top,[switch]$Basic,[string]$Scene='waveforms/example_two_pairs.json')
$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
$vivadoBin='E:/Xilinx/Vivado/2023.2/bin'
$fixture=Join-Path $taskRoot '.uart_sim/firing_scene_fixture'
$scenePath=if ([System.IO.Path]::IsPathRooted($Scene)) { $Scene } else { Join-Path $taskRoot $Scene }
& python "$taskRoot/tools/ad9106_firing.py" program --scene $scenePath --out $fixture
if ($LASTEXITCODE -ne 0) { throw 'PC fixture generation failed' }
$simDir=Join-Path $taskRoot $(if ($Basic) { if($Top){'.uart_sim/basic_top'}else{'.uart_sim/basic_sim'} } elseif ($Top) { '.uart_sim/firing_top' } else { '.uart_sim/firing_sim' })
$bench=if($Basic){'tb_basic_uart'}else{'tb_firing_uart'}
New-Item -ItemType Directory -Path $simDir -Force | Out-Null
Push-Location $simDir
try {
    $rtlDir=Join-Path $taskRoot 'AD9106_demo.srcs/sources_1/new'
    $bdDir=Join-Path $taskRoot 'AD9106_demo.gen/sources_1/bd/design_1'
    $testFiles=@("$rtlDir/ad9106_spi_writer.v","$rtlDir/AD9106.v","$rtlDir/uart_cmd_rx.v",
        "$rtlDir/ad9106_cmd_parser.v","$rtlDir/uart_cmd_tx.v","$taskRoot/AD9106_demo.srcs/sim_1/new/$bench.sv")
    $compileOptions=@('--sv')
    if ($Top) {
        foreach ($name in @('design_1_AD9106_0_0','design_1_ad9106_cmd_parser_0_0','design_1_uart_cmd_rx_0_0','design_1_uart_cmd_tx_0_0')) {
            $testFiles+="$bdDir/ip/$name/sim/$name.v"
        }
        $testFiles+=@("$bdDir/sim/design_1.v","$bdDir/hdl/design_1_wrapper.v",
            "$taskRoot/AD9106_demo.srcs/sim_1/new/clock_wizard_functional.sv")
    } else { $compileOptions+=@('--define','FIRING_FAST') }
    & "$vivadoBin/xvlog.bat" @compileOptions @testFiles
    if ($LASTEXITCODE -ne 0) { throw 'Firing xvlog failed' }
    & "$vivadoBin/xelab.bat" $bench -s firing_uart
    if ($LASTEXITCODE -ne 0) { throw 'Firing xelab failed' }
    & "$vivadoBin/xsim.bat" firing_uart -runall -log firing_uart.log
    if ($LASTEXITCODE -ne 0) { throw 'Firing xsim failed' }
    if (-not (Select-String -LiteralPath firing_uart.log -Pattern 'PASS FIRING SUMMARY:' -Quiet)) { throw 'Firing simulation did not report PASS' }
} finally { Pop-Location }
