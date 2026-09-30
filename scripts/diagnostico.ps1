<#
.SYNOPSIS
  Fabulim Studio: diagnostico da maquina (Windows). Nao instala nada e nao pede administrador.

.DESCRIPTION
  Coleta fatos do hardware e das ferramentas e grava config/hardware.json (so fatos, sem classificar).
  Se houver Python 3.10+, chama scripts/perfil.py para classificar o perfil (A a D) e gerar docs/AMBIENTE.md.

.PARAMETER Leve
  Modo leve (roda a cada inicializacao): pula o dxdiag e as sondas lentas, reaproveita a memoria da GPU da
  ultima coleta completa e avisa se a maquina mudou.

.PARAMETER Saida
  Caminho do JSON de saida (padrao: config\hardware.json).

.PARAMETER Docs
  Caminho do relatorio Markdown (padrao: docs\AMBIENTE.md).

.PARAMETER SemPerfil
  So coleta; nao chama o classificador em Python.

.PARAMETER Silencioso
  Sem mensagens de progresso.
#>
[CmdletBinding()]
param(
  [switch]$Leve,
  [string]$Saida,
  [string]$Docs,
  [switch]$SemPerfil,
  [switch]$Silencioso
)

$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

$Raiz = Split-Path -Parent $PSScriptRoot
if (-not $Saida) { $Saida = Join-Path $Raiz 'config\hardware.json' }
if (-not $Docs) { $Docs = Join-Path $Raiz 'docs\AMBIENTE.md' }
$Cultura = [System.Globalization.CultureInfo]::InvariantCulture

if (-not ('FabulimWin32' -as [type])) {
  Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class FabulimWin32 {
  [StructLayout(LayoutKind.Sequential)]
  public struct SYSTEM_POWER_STATUS {
    public byte ACLineStatus; public byte BatteryFlag; public byte BatteryLifePercent; public byte SystemStatusFlag;
    public int BatteryLifeTime; public int BatteryFullLifeTime;
  }
  [DllImport("kernel32.dll", SetLastError = true)]
  public static extern bool GetSystemPowerStatus(out SYSTEM_POWER_STATUS status);
  [DllImport("kernel32.dll")]
  public static extern bool IsProcessorFeaturePresent(uint feature);
}
'@
}

# ---------------------------------------------------------------- utilidades
function Escrever([string]$Msg) { if (-not $Silencioso) { Write-Host $Msg } }

function Executar-Comando {
  # Roda um executavel sem shell, com lista de argumentos e tempo limite. Nunca lanca excecao.
  param([string]$Exe, [string[]]$Argumentos = @(), [int]$TimeoutSeg = 15)
  $r = [ordered]@{ ok = $false; codigo = $null; saida = '' }
  try {
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $Exe
    $psi.Arguments = (($Argumentos | ForEach-Object { if ($_ -match '[\s"]') { '"' + ($_ -replace '"', '\"') + '"' } else { $_ } }) -join ' ')
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8
    $psi.StandardErrorEncoding = [System.Text.Encoding]::UTF8
    $p = [System.Diagnostics.Process]::Start($psi)
    $so = $p.StandardOutput.ReadToEndAsync()
    $se = $p.StandardError.ReadToEndAsync()
    if (-not $p.WaitForExit($TimeoutSeg * 1000)) {
      try { $p.Kill() } catch {}
      $r.saida = 'timeout'
      return $r
    }
    $p.WaitForExit()
    $r.codigo = $p.ExitCode
    $r.saida = (([string]$so.Result) + "`n" + ([string]$se.Result)).Trim()
    $r.ok = ($p.ExitCode -eq 0)
  }
  catch { $r.saida = $_.Exception.Message }
  return $r
}

function Localizar-Exe([string]$Nome, [string[]]$Alternativos = @()) {
  $c = Get-Command $Nome -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($c) { return $c.Source }
  foreach ($a in $Alternativos) { if ($a -and (Test-Path -LiteralPath $a)) { return $a } }
  return $null
}

function Obter-Ferramenta([string]$Nome, [string[]]$Alternativos = @(), [string[]]$ArgsVersao = @('--version')) {
  $o = [ordered]@{ installed = $false; version = $null; path = $null }
  $exe = Localizar-Exe $Nome $Alternativos
  if (-not $exe) { return $o }
  $o.installed = $true
  $o.path = $exe
  $r = Executar-Comando $exe $ArgsVersao 10
  if ($r.saida -match '(\d+\.\d+(?:\.\d+)?)') { $o.version = $Matches[1] }
  return $o
}

# ---------------------------------------------------------------- sistema, CPU, memoria, disco
function Obter-So {
  $os = $script:OsCim
  $arch = 'x64'
  try {
    if ([System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString() -eq 'Arm64') { $arch = 'arm64' }
  }
  catch {
    if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64' -or $env:PROCESSOR_ARCHITEW6432 -eq 'ARM64') { $arch = 'arm64' }
  }
  return [ordered]@{
    family = 'windows'
    name = ([string]$os.Caption).Trim()
    version = [string]$os.Version
    build = [int]$os.BuildNumber
    arch = $arch
  }
}

function Obter-PlanoEnergia {
  $r = Executar-Comando (Join-Path $env:WINDIR 'System32\powercfg.exe') @('/getactivescheme') 8
  $guid = $null; $rotulo = $null
  if ($r.saida -match '([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})') { $guid = $Matches[1].ToLower() }
  if ($r.saida -match '\(([^)]+)\)') { $rotulo = $Matches[1] }
  $conhecidos = @{
    '381b4222-f694-41f0-9685-ff5bb260df2e' = 'Equilibrado'
    '8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c' = 'Alto desempenho'
    'a1841308-3541-4fab-bc81-f71556f20b4a' = 'Economia de energia'
    'e9a42b02-d5df-448d-aa00-03f14749eb61' = 'Desempenho máximo'
  }
  $nome = if ($guid -and $conhecidos.ContainsKey($guid)) { $conhecidos[$guid] } else { $rotulo }
  return @{ nome = $nome; guid = $guid }
}

function Obter-Sistema {
  # -Property evita que o WMI calcule campos caros que nao usamos
  $cs = Get-CimInstance Win32_ComputerSystem -Property Manufacturer, Model, PCSystemType -ErrorAction SilentlyContinue
  $csp = Get-CimInstance Win32_ComputerSystemProduct -Property Version -ErrorAction SilentlyContinue
  $enc = Get-CimInstance Win32_SystemEnclosure -Property ChassisTypes -ErrorAction SilentlyContinue
  $pw = New-Object 'FabulimWin32+SYSTEM_POWER_STATUS'
  $okPw = $false
  try { $okPw = [FabulimWin32]::GetSystemPowerStatus([ref]$pw) } catch {}
  $temBateria = $okPw -and ($pw.BatteryFlag -ne 128) -and ($pw.BatteryFlag -ne 255)
  $naTomada = $null
  if ($okPw -and $pw.ACLineStatus -ne 255) { $naTomada = ($pw.ACLineStatus -eq 1) }
  $pct = $null
  if ($temBateria -and $pw.BatteryLifePercent -le 100) { $pct = [int]$pw.BatteryLifePercent }
  $chassi = @($enc | ForEach-Object { $_.ChassisTypes } | ForEach-Object { [int]$_ })
  $chassiPortatil = (@($chassi | Where-Object { @(8, 9, 10, 14, 30, 31, 32) -contains $_ }).Count -gt 0)
  $portatil = [bool]($temBateria -or $chassiPortatil -or ($cs.PCSystemType -eq 2))
  $comercial = ([string]$csp.Version).Trim()
  if (-not $comercial -or $comercial -match '^(None|System Version|Not Specified|To be filled.*|Default string|1\.0|0)$') { $comercial = $null }
  $plano = Obter-PlanoEnergia
  return [ordered]@{
    vendor = ([string]$cs.Manufacturer).Trim()
    model = ([string]$cs.Model).Trim()
    marketing_name = $comercial
    is_laptop = $portatil
    battery = [ordered]@{ present = [bool]$temBateria; percent = $pct; on_ac = $naTomada }
    power_plan = $plano.nome
    power_plan_guid = $plano.guid
  }
}

function Obter-Npu {
  $o = [ordered]@{ present = $false; name = $null }
  try {
    $d = @(Get-PnpDevice -PresentOnly -ErrorAction Stop | Where-Object {
        $_.Class -in @('ComputeAccelerator', 'NPU') -or $_.FriendlyName -match '\bNPU\b|AI Boost|Neural|Hexagon|\bIPU\b|XDNA|Ryzen AI'
      } | Select-Object -First 1)
    if ($d.Count -gt 0) { $o.present = $true; $o.name = [string]$d[0].FriendlyName }
  }
  catch {}
  return $o
}

function Obter-Cpu([bool]$Completo, $Anterior) {
  $procs = @(Get-CimInstance Win32_Processor -Property Name, NumberOfCores, NumberOfLogicalProcessors, MaxClockSpeed -ErrorAction SilentlyContinue)
  $nome = if ($procs.Count -gt 0) { ([string]$procs[0].Name -replace '\s+', ' ').Trim() } else { 'desconhecida' }
  $nucleos = [int](($procs | Measure-Object -Property NumberOfCores -Sum).Sum)
  $threads = [int](($procs | Measure-Object -Property NumberOfLogicalProcessors -Sum).Sum)
  $tem = { param($n) try { [bool][FabulimWin32]::IsProcessorFeaturePresent([uint32]$n) } catch { $false } }
  return [ordered]@{
    model = $nome
    cores = $nucleos
    threads = $threads
    max_mhz = if ($procs.Count -gt 0) { [int]$procs[0].MaxClockSpeed } else { $null }
    features = [ordered]@{
      avx = (& $tem 39); avx2 = (& $tem 40); avx512 = (& $tem 41); sse42 = (& $tem 38); neon = (& $tem 19)
    }
    # Get-PnpDevice e lento; no modo leve reaproveita a ultima coleta
    npu = if (-not $Completo -and $Anterior -and $Anterior.cpu.npu) { [ordered]@{ present = [bool]$Anterior.cpu.npu.present; name = $Anterior.cpu.npu.name } } else { Obter-Npu }
  }
}

function Obter-Memoria {
  $os = $script:OsCim
  return [ordered]@{
    ram_total_mb = [int][math]::Round([double]$os.TotalVisibleMemorySize / 1024)
    ram_free_mb = [int][math]::Round([double]$os.FreePhysicalMemory / 1024)
  }
}

function Obter-Disco([string]$Caminho, [bool]$Completo, $Anterior) {
  $o = [ordered]@{ path = $Caminho; drive = $null; total_mb = 0; free_mb = 0; kind = 'desconhecido' }
  try {
    $letra = Split-Path -Qualifier $Caminho
    $di = New-Object System.IO.DriveInfo($letra)
    $o.drive = $letra
    $o.total_mb = [int64][math]::Floor($di.TotalSize / 1MB)
    $o.free_mb = [int64][math]::Floor($di.AvailableFreeSpace / 1MB)
  }
  catch {}
  if (-not $Completo -and $Anterior -and $Anterior.disk.kind -and $Anterior.disk.drive -eq $o.drive) {
    $o.kind = [string]$Anterior.disk.kind
    return $o
  }
  try {
    $disco = Get-Partition -DriveLetter $o.drive.TrimEnd(':') -ErrorAction Stop | Get-Disk -ErrorAction Stop
    $fis = Get-PhysicalDisk -ErrorAction Stop | Where-Object { $_.DeviceId -eq [string]$disco.Number } | Select-Object -First 1
    if ($fis) { $o.kind = ('{0} ({1})' -f $fis.MediaType, $fis.BusType) }
  }
  catch {}
  return $o
}

# ---------------------------------------------------------------- GPU e aceleracao
function Ler-Dxdiag {
  # Devolve a memoria dedicada/compartilhada de cada adaptador (o WMI nao informa memoria compartilhada).
  $lista = @()
  $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ('fabulim_dxdiag_{0}.txt' -f [guid]::NewGuid().ToString('N'))
  try {
    $p = Start-Process -FilePath (Join-Path $env:WINDIR 'System32\dxdiag.exe') -ArgumentList @('/whql:off', '/t', $tmp) -WindowStyle Hidden -PassThru -ErrorAction Stop
    if (-not $p.WaitForExit(90000)) { try { $p.Kill() } catch {}; return @() }
    if (-not (Test-Path -LiteralPath $tmp)) { return @() }
    $bytes = [System.IO.File]::ReadAllBytes($tmp)
    $enc = if ($bytes.Length -ge 2 -and $bytes[0] -eq 0xFF -and $bytes[1] -eq 0xFE) { [System.Text.Encoding]::Unicode } else { [System.Text.Encoding]::UTF8 }
    $linhas = $enc.GetString($bytes) -split "`r?`n"
    $dentro = $false; $atual = $null
    foreach ($l in $linhas) {
      if ($l -match '^Display Devices') { $dentro = $true; continue }
      if ($dentro -and $l -match '^(Sound Devices|Sound Capture Devices|DirectInput Devices|Video Capture Devices)') { break }
      if (-not $dentro) { continue }
      if ($l -match '^\s*Card name:\s*(.+?)\s*$') {
        $atual = [ordered]@{ name = $Matches[1]; dedicated_mb = $null; shared_mb = $null; driver_model = $null; d3d12_ml = $false }
        $lista += , $atual
      }
      elseif ($atual) {
        if ($l -match '^\s*Dedicated Memory:\s*(\d+)') { $atual.dedicated_mb = [int64]$Matches[1] }
        elseif ($l -match '^\s*Shared Memory:\s*(\d+)') { $atual.shared_mb = [int64]$Matches[1] }
        elseif ($l -match '^\s*Driver Model:\s*(.+?)\s*$') { $atual.driver_model = $Matches[1] }
        elseif ($l -match '^\s*Adapter Attributes:.*D3D12_GENERIC_ML') { $atual.d3d12_ml = $true }
      }
    }
  }
  catch {}
  finally { Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue }
  return $lista
}

function Obter-NvidiaSmi {
  $exe = Localizar-Exe 'nvidia-smi' @((Join-Path $env:WINDIR 'System32\nvidia-smi.exe'), (Join-Path $env:ProgramFiles 'NVIDIA Corporation\NVSMI\nvidia-smi.exe'))
  if (-not $exe) { return $null }
  $q = Executar-Comando $exe @('--query-gpu=name,memory.total,driver_version', '--format=csv,noheader,nounits') 10
  if (-not $q.ok) { return $null }
  $cabecalho = Executar-Comando $exe @() 10
  $cuda = $null
  if ($cabecalho.saida -match 'CUDA Version:\s*([\d\.]+)') { $cuda = $Matches[1] }
  $gpus = @()
  foreach ($l in ($q.saida -split "`r?`n")) {
    $c = $l -split ',\s*'
    if ($c.Count -ge 3 -and $c[1] -match '^\d+$') { $gpus += , [ordered]@{ name = $c[0].Trim(); vram_mb = [int64]$c[1]; driver = $c[2].Trim() } }
  }
  return @{ cuda = $cuda; gpus = $gpus; exe = $exe }
}

function Obter-Vulkan {
  $o = [ordered]@{ available = $false; api_version = $null; devices = @() }
  $exe = Localizar-Exe 'vulkaninfo'
  $dll = Test-Path -LiteralPath (Join-Path $env:WINDIR 'System32\vulkan-1.dll')
  if ($exe) {
    $r = Executar-Comando $exe @('--summary') 20
    if ($r.saida -match 'Vulkan Instance Version:\s*([\d\.]+)') { $o.api_version = $Matches[1] }
    $devs = @(); $atual = $null
    foreach ($l in ($r.saida -split "`r?`n")) {
      if ($l -match '^GPU\d+:') { $atual = [ordered]@{ name = $null; type = $null }; $devs += , $atual }
      elseif ($atual -and $l -match '^\s*deviceName\s*=\s*(.+?)\s*$') { $atual.name = $Matches[1] }
      elseif ($atual -and $l -match '^\s*deviceType\s*=\s*PHYSICAL_DEVICE_TYPE_(\w+)') { $atual.type = $Matches[1].ToLower() }
    }
    $o.devices = @($devs)
    $o.available = ($devs.Count -gt 0)
  }
  elseif ($dll) { $o.available = $true }
  return $o
}

function Obter-Gpus([bool]$Completo, $Anterior, $Nvidia, $Vulkan) {
  $dx = if ($Completo) { @(Ler-Dxdiag) } else { @() }
  $lista = @()
  $ctrl = @(Get-CimInstance Win32_VideoController -Property Name, PNPDeviceID, DriverVersion, DriverDate -ErrorAction SilentlyContinue)
  foreach ($c in $ctrl) {
    $nome = ([string]$c.Name).Trim()
    if (-not $nome -or $nome -match 'Basic (Render|Display)|Remote Display|Hyper-V|Virtual|Meta Virtual|Parsec|Mirage|Citrix|DisplayLink|Indirect Display') { continue }
    $pnp = [string]$c.PNPDeviceID
    $ven = if ($pnp -match 'VEN_([0-9A-Fa-f]{4})') { $Matches[1].ToUpper() } else { '' }
    $fab = switch ($ven) { '8086' { 'intel' } '10DE' { 'nvidia' } '1002' { 'amd' } '1022' { 'amd' } '106B' { 'apple' } default { 'unknown' } }
    $dedicado = $null; $compartilhado = $null; $modelo = $null; $ml = $null

    # 1) NVIDIA: nvidia-smi e a fonte mais confiavel
    if ($fab -eq 'nvidia' -and $Nvidia) {
      $n = $Nvidia.gpus | Where-Object { $nome -like ('*' + $_.name + '*') -or $_.name -like ('*' + $nome + '*') } | Select-Object -First 1
      if ($n) { $dedicado = $n.vram_mb }
    }
    # 2) dxdiag (modo completo): dedicada e compartilhada
    $d = $dx | Where-Object { $_.name -eq $nome } | Select-Object -First 1
    if ($d) {
      if ($null -eq $dedicado) { $dedicado = $d.dedicated_mb }
      $compartilhado = $d.shared_mb; $modelo = $d.driver_model; $ml = $d.d3d12_ml
    }
    # 3) registro (QWORD): confiavel para placas dedicadas AMD/Intel
    if ($null -eq $dedicado) {
      try {
        $base = 'HKLM:\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}'
        foreach ($k in (Get-ChildItem $base -ErrorAction Stop | Where-Object { $_.PSChildName -match '^\d{4}$' })) {
          $prop = Get-ItemProperty $k.PSPath -ErrorAction SilentlyContinue
          if ($prop.DriverDesc -eq $nome -and $null -ne $prop.'HardwareInformation.qwMemorySize') {
            $q = $prop.'HardwareInformation.qwMemorySize'
            $bytes = if ($q -is [byte[]]) { [BitConverter]::ToUInt64(([byte[]]($q + (New-Object byte[] 8)))[0..7], 0) } else { [uint64]$q }
            if ($bytes -gt 0) { $dedicado = [int64]($bytes / 1MB) }
          }
        }
      }
      catch {}
    }
    # 4) modo leve: reaproveita a coleta anterior (mesmo nome e driver)
    if (-not $Completo -and $Anterior -and $null -eq $dedicado) {
      $ant = @($Anterior.gpus) | Where-Object { $_.name -eq $nome -and $_.driver -eq [string]$c.DriverVersion } | Select-Object -First 1
      if ($ant) { $dedicado = $ant.dedicated_mb; $compartilhado = $ant.shared_mb; $modelo = $ant.driver_model; $ml = $ant.d3d12_ml }
    }
    # tipo: so quando o Vulkan informa (o classificador infere o resto por fabricante e nome)
    $tipo = $null
    $vk = @($Vulkan.devices) | Where-Object { $_.name -eq $nome } | Select-Object -First 1
    if ($vk -and $vk.type -eq 'integrated_gpu') { $tipo = 'integrated' }
    elseif ($vk -and $vk.type -eq 'discrete_gpu') { $tipo = 'discrete' }

    $lista += , [ordered]@{
      vendor = $fab
      name = $nome
      kind = $tipo
      dedicated_mb = $dedicado
      shared_mb = $compartilhado
      driver = [string]$c.DriverVersion
      driver_date = if ($c.DriverDate) { ([datetime]$c.DriverDate).ToString('yyyy-MM-dd', $Cultura) } else { $null }
      driver_model = $modelo
      d3d12_ml = $ml
      pci_id = if ($pnp -match '(VEN_[0-9A-Fa-f]{4}&DEV_[0-9A-Fa-f]{4})') { $Matches[1] } else { $null }
      gfx_arch = $null
      gfx_arch_source = $null
    }
  }
  return $lista
}

function Obter-Aceleracao($Gpus, $Nvidia, $Vulkan, [bool]$Completo, $Python) {
  $cuda = [ordered]@{ available = $false; detail = $null; version = $null }
  if ($Nvidia -and @($Nvidia.gpus).Count -gt 0) {
    $cuda.available = $true; $cuda.version = $Nvidia.cuda
    $cuda.detail = ('driver {0}; CUDA {1}' -f $Nvidia.gpus[0].driver, $Nvidia.cuda)
  }
  $rocm = [ordered]@{ available = $false; detail = $null; version = $null }
  if ($env:HIP_PATH -and (Test-Path -LiteralPath (Join-Path $env:HIP_PATH 'bin\hipInfo.exe'))) {
    $rocm.available = $true; $rocm.detail = 'HIP SDK encontrado (HIP_PATH)'
  }
  $dml = [ordered]@{ available = $false; detail = $null; version = $null }
  if (Test-Path -LiteralPath (Join-Path $env:WINDIR 'System32\DirectML.dll')) {
    $dml.available = $true
    $ml = @($Gpus) | Where-Object { $_.d3d12_ml -eq $true } | Select-Object -First 1
    $dml.detail = if ($ml) { 'DirectML.dll presente; adaptador com D3D12 ML' } else { 'DirectML.dll presente; suporte D3D12 ML do adaptador nao verificado' }
  }
  $metal = [ordered]@{ available = $false; detail = $null; version = $null }
  $ov = [ordered]@{ available = $false; candidate = $false; version = $null }
  $temIntel = (@($Gpus) | Where-Object { $_.vendor -eq 'intel' }).Count -gt 0
  $ov.candidate = [bool]$temIntel
  if ($Completo -and $Python -and $Python.path) {
    $r = Executar-Comando $Python.path @('-c', 'import openvino; print(openvino.__version__)') 25
    if ($r.ok -and $r.saida -match '(\d+\.\d+[\w\.\-]*)') { $ov.available = $true; $ov.version = $Matches[1] }
  }
  return [ordered]@{ cuda = $cuda; rocm = $rocm; directml = $dml; vulkan = $Vulkan; metal = $metal; openvino = $ov }
}

# ---------------------------------------------------------------- ferramentas
function Obter-Python {
  $o = [ordered]@{ installed = $false; version = $null; path = $null; versions_available = @() }
  # ignora o atalho da Microsoft Store (WindowsApps), que so abre a loja
  $c = Get-Command python -CommandType Application -ErrorAction SilentlyContinue | Where-Object { $_.Source -notmatch 'WindowsApps' } | Select-Object -First 1
  if ($c) {
    $o.installed = $true; $o.path = $c.Source
    $r = Executar-Comando $c.Source @('--version') 10
    if ($r.saida -match '(\d+\.\d+\.\d+)') { $o.version = $Matches[1] }
  }
  $py = Localizar-Exe 'py'
  if ($py) {
    $r = Executar-Comando $py @('-0p') 10
    $versoes = @()
    foreach ($l in ($r.saida -split "`r?`n")) {
      if ($l -match '^\s*-(?:V:)?(\d+\.\d+)\S*\s+\*?\s*(.+?)\s*$') {
        $versoes += $Matches[1]
        if (-not $o.installed) { $o.installed = $true; $o.path = $Matches[2]; $o.version = $Matches[1] }
      }
    }
    $o.versions_available = @($versoes | Select-Object -Unique)
  }
  return $o
}

function Obter-Ffmpeg {
  $o = [ordered]@{ installed = $false; version = $null; path = $null; encoders = @() }
  $local = Join-Path $Raiz 'tools\ffmpeg\bin\ffmpeg.exe'; $exe = if (Test-Path -LiteralPath $local) { $local } else { Localizar-Exe 'ffmpeg' }
  if (-not $exe) { return $o }
  $o.installed = $true; $o.path = $exe
  $r = Executar-Comando $exe @('-version') 10
  if ($r.saida -match 'ffmpeg version (\S+)') { $o.version = $Matches[1] }
  $e = Executar-Comando $exe @('-hide_banner', '-encoders') 15
  $o.encoders = @('libx264', 'h264_qsv', 'h264_nvenc', 'h264_amf', 'h264_videotoolbox' | Where-Object { $e.saida -match ('\b' + $_ + '\b') })
  return $o
}

function Obter-Ollama {
  $o = [ordered]@{
    installed = $false; version = $null; path = $null; server_active = $false; host = '127.0.0.1:11434'
    models = @(); loaded = @(); gpu_discovery = @(); igpu_dropped = $false
  }
  $exe = Localizar-Exe 'ollama' @((Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'))
  if (-not $exe) { return $o }
  $o.installed = $true; $o.path = $exe
  try {
    $v = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/version' -TimeoutSec 2 -ErrorAction Stop
    $o.server_active = $true; $o.version = [string]$v.version
    $t = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 3 -ErrorAction Stop
    $o.models = @($t.models | ForEach-Object { [ordered]@{ name = [string]$_.name; size_mb = [int64][math]::Round([double]$_.size / 1MB) } })
    $ps = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/ps' -TimeoutSec 3 -ErrorAction Stop
    $o.loaded = @($ps.models | ForEach-Object { [ordered]@{ name = [string]$_.name; size_mb = [int64][math]::Round([double]$_.size / 1MB); size_vram_mb = [int64][math]::Round([double]$_.size_vram / 1MB) } })
  }
  catch {
    $r = Executar-Comando $exe @('--version') 8
    if ($r.saida -match 'version is (\d+\.\d+\.\d+)') { $o.version = $Matches[1] }
  }
  # o log do servidor diz quais GPUs o Ollama enxergou e se descartou a integrada; o bloco de descoberta
  # fica no inicio da sessao do servidor, longe do fim do arquivo, entao busca no arquivo todo
  $log = Join-Path $env:LOCALAPPDATA 'Ollama\server.log'
  if (Test-Path -LiteralPath $log) {
    $linhas = @(Select-String -LiteralPath $log -Pattern 'discovering available GPUs|dropping integrated GPU|msg="inference compute"' -ErrorAction SilentlyContinue |
        Select-Object -Last 40 | ForEach-Object { $_.Line })
    $inicio = 0
    for ($i = 0; $i -lt $linhas.Count; $i++) { if ($linhas[$i] -match 'discovering available GPUs') { $inicio = $i } }
    $achados = @()
    foreach ($l in @($linhas | Select-Object -Skip $inicio)) {
      $descartada = $l -match 'dropping integrated GPU'
      if (($descartada -or $l -match 'msg="inference compute"') -and $l -match 'library=(\S+)\s.*?description=(?:"([^"]+)"|(\S+))') {
        $nomeGpu = if ($Matches[2]) { $Matches[2] } else { $Matches[3] }
        $achados += , [ordered]@{ library = $Matches[1]; name = $nomeGpu; dropped_integrated = [bool]$descartada }
        if ($descartada) { $o.igpu_dropped = $true }
      }
    }
    $o.gpu_discovery = @($achados)
  }
  return $o
}

function Obter-ClaudeCode {
  $o = [ordered]@{ installed = $false; version = $null; path = $null; source = $null; logged_in = $null; auth_method = $null; subscription = $null }
  $exe = Localizar-Exe 'claude'
  if ($exe) { $o.source = 'path' }
  else {
    # o app Claude (desktop) embute o Claude Code fora do PATH
    $base = Join-Path $env:APPDATA 'Claude\claude-code'
    $dirs = @(Get-ChildItem -LiteralPath $base -Directory -ErrorAction SilentlyContinue)
    $ord = $dirs | Sort-Object { try { [version]$_.Name } catch { [version]'0.0' } } -Descending
    foreach ($d in $ord) {
      $e = Join-Path $d.FullName 'claude.exe'
      if (Test-Path -LiteralPath $e) { $exe = $e; $o.source = 'app'; break }
    }
  }
  if (-not $exe) { return $o }
  $o.installed = $true; $o.path = $exe
  $v = Executar-Comando $exe @('--version') 15
  if ($v.saida -match '(\d+\.\d+\.\d+)') { $o.version = $Matches[1] }
  # `claude auth status` e o caminho oficial; nunca leimos arquivos de credencial. Guardamos so o essencial.
  $a = Executar-Comando $exe @('auth', 'status') 20
  $txt = [string]$a.saida
  $i = $txt.IndexOf('{'); $k = $txt.LastIndexOf('}')
  if ($i -ge 0 -and $k -gt $i) {
    try {
      $j = $txt.Substring($i, $k - $i + 1) | ConvertFrom-Json
      $o.logged_in = [bool]$j.loggedIn
      $o.auth_method = [string]$j.authMethod
      $o.subscription = [string]$j.subscriptionType
    }
    catch {}
  }
  return $o
}

function Obter-Impressao($Hw) {
  $partes = @($Hw.cpu.model, $Hw.memory.ram_total_mb, $Hw.os.build, $Hw.system.is_laptop) + @($Hw.gpus | ForEach-Object { '{0}|{1}' -f $_.name, $_.driver })
  $sha = [System.Security.Cryptography.SHA256]::Create()
  $h = $sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes(($partes -join ';')))
  return ((($h | ForEach-Object { $_.ToString('x2') }) -join '').Substring(0, 16))
}

function Localizar-PythonParaPerfil {
  $cands = @()
  $py = Localizar-Exe 'py'
  if ($py) { foreach ($v in @('-3.12', '-3.13', '-3')) { $cands += , @($py, $v) } }
  foreach ($n in @('python', 'python3')) {
    $c = Get-Command $n -CommandType Application -ErrorAction SilentlyContinue | Where-Object { $_.Source -notmatch 'WindowsApps' } | Select-Object -First 1
    if ($c) { $cands += , @($c.Source) }
  }
  foreach ($c in $cands) {
    $extra = @($c | Select-Object -Skip 1)
    $r = Executar-Comando $c[0] ($extra + @('-c', 'import sys; print(sys.version_info[0] * 100 + sys.version_info[1])')) 10
    if ($r.ok -and $r.saida -match '^\d+$' -and [int]$r.saida -ge 310) { return , $c }
  }
  return $null
}

# ---------------------------------------------------------------- fluxo principal
$t0 = Get-Date
$completo = -not $Leve
$anterior = $null
if (Test-Path -LiteralPath $Saida) {
  try { $anterior = Get-Content -LiteralPath $Saida -Raw -Encoding UTF8 | ConvertFrom-Json } catch { $anterior = $null }
}
if ($Leve -and -not $anterior) {
  Escrever 'Modo leve sem coleta anterior: fazendo o diagnóstico completo.'
  $completo = $true
}
Escrever ('Fabulim Studio: diagnóstico da máquina ({0})' -f $(if ($completo) { 'completo' } else { 'leve' }))

# Uma consulta so ao sistema operacional serve para "os" e "memory"
$script:OsCim = Get-CimInstance Win32_OperatingSystem -Property Caption, Version, BuildNumber, TotalVisibleMemorySize, FreePhysicalMemory -ErrorAction SilentlyContinue

# Modo leve: refaz so o que muda toda hora (memoria livre, bateria, Ollama). Aceleracao e ferramentas
# vem da ultima coleta; se o hardware mudar, a impressao digital muda e o aviso aparece.
$reusar = (-not $completo) -and $anterior -and $anterior.tools -and $anterior.acceleration
if ($reusar) {
  $nvidia = $null
  $vulkan = $anterior.acceleration.vulkan
  $python = $anterior.tools.python
}
else {
  $nvidia = Obter-NvidiaSmi
  $vulkan = Obter-Vulkan
  $python = Obter-Python
}
$gpus = @(Obter-Gpus $completo $anterior $nvidia $vulkan)

$agora = (Get-Date).ToString('yyyy-MM-ddTHH:mm:ssK', $Cultura)
$hw = [ordered]@{
  schema_version = 1
  collected_at = $agora
  full_collected_at = if ($completo) { $agora } elseif ($anterior.full_collected_at) { [string]$anterior.full_collected_at } else { [string]$anterior.collected_at }
  mode = if ($completo) { 'full' } else { 'light' }
  os = Obter-So
  system = Obter-Sistema
  cpu = Obter-Cpu $completo $anterior
  memory = Obter-Memoria
  disk = Obter-Disco $Raiz $completo $anterior
  gpus = $gpus
  acceleration = if ($reusar) { $anterior.acceleration } else { Obter-Aceleracao $gpus $nvidia $vulkan $completo $python }
  tools = if ($reusar) {
    [ordered]@{
      python = $python
      node = $anterior.tools.node
      npm = $anterior.tools.npm
      git = $anterior.tools.git
      ffmpeg = Obter-Ffmpeg
      ollama = Obter-Ollama
      claude_code = $anterior.tools.claude_code
    }
  }
  else {
    [ordered]@{
      python = $python
      node = Obter-Ferramenta 'node'
      npm = Obter-Ferramenta 'npm.cmd'
      git = Obter-Ferramenta 'git'
      ffmpeg = Obter-Ffmpeg
      ollama = Obter-Ollama
      claude_code = Obter-ClaudeCode
    }
  }
}
$hw.fingerprint = Obter-Impressao $hw
$mudou = $false
if ($anterior -and $anterior.fingerprint -and $anterior.fingerprint -ne $hw.fingerprint) { $mudou = $true }
$hw.changed_since_last_run = $mudou

$dirSaida = Split-Path -Parent $Saida
if ($dirSaida -and -not (Test-Path -LiteralPath $dirSaida)) { New-Item -ItemType Directory -Force -Path $dirSaida | Out-Null }
$json = ConvertTo-Json -InputObject $hw -Depth 8
[System.IO.File]::WriteAllText($Saida, $json, (New-Object System.Text.UTF8Encoding($false)))

$g0 = if ($gpus.Count -gt 0) { $gpus[0] } else { $null }
Escrever ('  Sistema : {0} ({1})' -f $hw.os.name, $hw.os.arch)
Escrever ('  Máquina : {0} {1}{2}' -f $hw.system.vendor, $(if ($hw.system.marketing_name) { $hw.system.marketing_name } else { $hw.system.model }), $(if ($hw.system.is_laptop) { ' (notebook)' } else { '' }))
Escrever ('  CPU     : {0} ({1} núcleos, {2} threads)' -f $hw.cpu.model, $hw.cpu.cores, $hw.cpu.threads)
Escrever ('  RAM     : {0} MB total, {1} MB livres' -f $hw.memory.ram_total_mb, $hw.memory.ram_free_mb)
if ($g0) { Escrever ('  GPU     : {0} (dedicada: {1} MB; compartilhada: {2} MB)' -f $g0.name, $g0.dedicated_mb, $g0.shared_mb) } else { Escrever '  GPU     : nenhuma detectada' }
Escrever ('  Disco   : {0:N1} GB livres em {1}' -f ($hw.disk.free_mb / 1024), $hw.disk.drive)
Escrever ('  Salvo em: {0}' -f $Saida)
if ($mudou) {
  Escrever 'AVISO: a máquina mudou desde a última coleta (CPU, RAM, GPU/driver ou sistema). Rode scripts\diagnostico.ps1 sem -Leve para refazer o perfil.'
}

if (-not $SemPerfil) {
  $pyPerfil = Localizar-PythonParaPerfil
  if ($pyPerfil) {
    $extra = @($pyPerfil | Select-Object -Skip 1)
    $argsPerfil = @((Join-Path $Raiz 'scripts\perfil.py'), '--hardware', $Saida)
    if ($completo) { $argsPerfil += @('--docs', $Docs) } else { $argsPerfil += '--sem-docs' }
    & $pyPerfil[0] @extra @argsPerfil
  }
  else {
    Escrever 'Python 3.10+ não encontrado: coleta feita, mas o perfil não foi classificado (instale o Python 3.12 e rode de novo).'
  }
}
Escrever ('Concluído em {0:N1} s.' -f ((Get-Date) - $t0).TotalSeconds)
