$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
$vivadoBin='E:/Xilinx/Vivado/2023.2/bin'
$simDir=Join-Path $taskRoot '.uart_sim/stream_budget'
New-Item -ItemType Directory -Path $simDir -Force | Out-Null
Push-Location $simDir
try {
    & "$vivadoBin/xvlog.bat" --sv "$taskRoot/AD9106_demo.srcs/sources_1/new/ad9106_spi_writer.v" "$taskRoot/AD9106_demo.srcs/sources_1/new/AD9106.v" "$taskRoot/AD9106_demo.srcs/sim_1/new/tb_stream_budget.sv"
    if ($LASTEXITCODE -ne 0) { throw 'Budget compile failed' }
    & "$vivadoBin/xelab.bat" tb_stream_budget -s stream_budget
    if ($LASTEXITCODE -ne 0) { throw 'Budget elaboration failed' }
    & "$vivadoBin/xsim.bat" stream_budget -runall -log stream_budget.log
    if ($LASTEXITCODE -ne 0 -or -not (Select-String -LiteralPath stream_budget.log -Pattern 'PASS STREAM BUDGET' -Quiet)) { throw 'Budget simulation failed' }
} finally { Pop-Location }
