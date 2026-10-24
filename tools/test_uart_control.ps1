$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$vivadoBin = 'E:/Xilinx/Vivado/2023.2/bin'
$simDir = Join-Path $taskRoot '.uart_sim'
New-Item -ItemType Directory -Path $simDir -Force | Out-Null
Push-Location $simDir
try {
    $rtlDir = Join-Path $taskRoot 'AD9106_demo.srcs/sources_1/new'
    & "$vivadoBin/xvlog.bat" --sv "$rtlDir/ad9106_spi_writer.v" "$rtlDir/AD9106.v" "$rtlDir/uart_cmd_rx.v" "$rtlDir/ad9106_cmd_parser.v" "$rtlDir/uart_cmd_tx.v" "$taskRoot/AD9106_demo.srcs/sim_1/new/tb_uart_control.sv"
    if ($LASTEXITCODE -ne 0) { throw 'xvlog failed' }
    & "$vivadoBin/xelab.bat" tb_uart_control -s uart_control_sim
    if ($LASTEXITCODE -ne 0) { throw 'xelab failed' }
    & "$vivadoBin/xsim.bat" uart_control_sim -runall -log uart_control.log
    if ($LASTEXITCODE -ne 0) { throw 'xsim failed' }
    if (-not (Select-String -LiteralPath uart_control.log -Pattern 'PASS: UART -> parser' -Quiet)) {
        throw 'Simulation did not report PASS'
    }
} finally { Pop-Location }
