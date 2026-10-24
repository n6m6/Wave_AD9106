param([switch]$InitOnly, [switch]$FunctionalClock, [switch]$ClockOnly)
$ErrorActionPreference = 'Stop'
if ($ClockOnly -and $FunctionalClock) { throw '-ClockOnly requires the vendor clock model; omit -FunctionalClock.' }
$taskRoot = Split-Path -Parent $PSScriptRoot
$vivadoBin = 'E:/Xilinx/Vivado/2023.2/bin'
$simName = if ($ClockOnly) { 'clock_vendor' } elseif ($FunctionalClock) { 'top_fast' } else { 'top' }
$simDir = Join-Path $taskRoot ".uart_sim/$simName"
New-Item -ItemType Directory -Path $simDir -Force | Out-Null
Push-Location $simDir
try {
    $rtlDir = Join-Path $taskRoot 'AD9106_demo.srcs/sources_1/new'
    $bdDir = Join-Path $taskRoot 'AD9106_demo.gen/sources_1/bd/design_1'
    $designFiles = @(
        "$rtlDir/ad9106_spi_writer.v", "$rtlDir/AD9106.v", "$rtlDir/uart_cmd_rx.v",
        "$rtlDir/ad9106_cmd_parser.v", "$rtlDir/uart_cmd_tx.v",
        "$bdDir/ip/design_1_AD9106_0_0/sim/design_1_AD9106_0_0.v",
        "$bdDir/ip/design_1_ad9106_cmd_parser_0_0/sim/design_1_ad9106_cmd_parser_0_0.v",
        "$bdDir/ip/design_1_uart_cmd_rx_0_0/sim/design_1_uart_cmd_rx_0_0.v",
        "$bdDir/ip/design_1_uart_cmd_tx_0_0/sim/design_1_uart_cmd_tx_0_0.v",
        "$bdDir/ip/design_1_clk_wiz_0/design_1_clk_wiz_0_clk_wiz.v",
        "$bdDir/ip/design_1_clk_wiz_0/design_1_clk_wiz_0.v",
        "$bdDir/sim/design_1.v", "$bdDir/hdl/design_1_wrapper.v",
        "$taskRoot/AD9106_demo.srcs/sim_1/new/tb_top_uart.sv",
        "$taskRoot/AD9106_demo.srcs/sim_1/new/tb_ad9106.v",
        "$taskRoot/AD9106_demo.srcs/sim_1/new/tb_clock_wizard.sv",
        'E:/Xilinx/Vivado/2023.2/data/verilog/src/glbl.v'
    )
    if ($FunctionalClock) {
        Write-Output 'Functional clock model selected: production RTL parameters and BD wiring retained; vendor MMCM excluded.'
        $designFiles = @($designFiles | Where-Object { $_ -notlike '*design_1_clk_wiz_0*' })
        $designFiles += "$taskRoot/AD9106_demo.srcs/sim_1/new/clock_wizard_functional.sv"
    }
    foreach ($designFile in $designFiles) {
        if (-not (Test-Path -LiteralPath $designFile)) { throw "Missing generated source: $designFile. Generate BD Output Products first." }
    }
    & "$vivadoBin/xvlog.bat" --sv @designFiles
    if ($LASTEXITCODE -ne 0) { throw 'Top xvlog failed' }
    $testTop = if ($ClockOnly) { 'tb_clock_wizard' } elseif ($InitOnly) { 'tb_ad9106' } else { 'tb_top_uart' }
    & "$vivadoBin/xelab.bat" --debug typical --relax --mt 2 -L unisims_ver -L unimacro_ver -L secureip -L xpm $testTop glbl -s $testTop
    if ($LASTEXITCODE -ne 0) { throw 'Top xelab failed' }
    & "$vivadoBin/xsim.bat" $testTop -runall -log "${testTop}.log"
    if ($LASTEXITCODE -ne 0) { throw 'Top xsim failed' }
    $passPattern = if ($ClockOnly) { 'PASS CLOCK SUMMARY:' } elseif ($InitOnly) { 'PASS: AD9106 init completed' } else { 'PASS TOP SUMMARY:' }
    if (-not (Select-String -LiteralPath "${testTop}.log" -Pattern $passPattern -Quiet)) {
        throw 'Top simulation did not report PASS'
    }
} finally { Pop-Location }
