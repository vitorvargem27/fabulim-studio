<#
.SYNOPSIS
  Medicao do LLM local no Ollama: CPU (servidor padrao) contra iGPU via Vulkan (servidor temporario).

.DESCRIPTION
  Reproduz as medicoes registradas em docs/MODELOS.md. Nao baixa nada: usa um modelo que ja esteja instalado.
  O servidor temporario sobe na porta 11435 com OLLAMA_IGPU_ENABLE=1 SO PARA ESTE PROCESSO (nao altera variaveis
  globais nem o seu Ollama) e e encerrado no fim.

.PARAMETER Modelo
  Modelo instalado (padrao: qwen3:4b).
#>
[CmdletBinding()]
param([string]$Modelo = 'qwen3:4b')

$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}
$ollama = (Get-Command ollama).Source
$tmp = Join-Path ([IO.Path]::GetTempPath()) ('fabulim_bench_' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $tmp | Out-Null

$curto = 'Responda somente com JSON valido em portugues do Brasil, sem explicacoes. Crie uma cena curta para criancas de 3 anos: um coelho azul chamado Bolinho descobre a cor amarela num campo de girassois. Campos: titulo, fala_do_narrador, acao_do_personagem.'
$paragrafo = 'O coelho Bolinho acordou cedo, esticou as orelhas e foi ate o campo. La ele viu flores grandes, redondas e brilhantes. A borboleta Lili contou que aquela cor se chama amarelo, a mesma cor do sol. Bolinho riu, pulou tres vezes e abracou um girassol. '
$longo = ($paragrafo * 12) + ' Com base na historia acima, escreva em JSON o titulo e uma fala curta do narrador, sem explicacoes.'

function Invoke-Gen($base, $prompt, $numPredict) {
  $corpo = @{ model = $Modelo; prompt = $prompt; stream = $false; think = $false; keep_alive = '10m'
              options = @{ temperature = 0; num_predict = $numPredict; seed = 1 } }
  $bytes = [Text.Encoding]::UTF8.GetBytes(($corpo | ConvertTo-Json -Depth 5))
  $sw = [Diagnostics.Stopwatch]::StartNew()
  $r = Invoke-RestMethod -Uri "$base/api/generate" -Method Post -Body $bytes -ContentType 'application/json; charset=utf-8' -TimeoutSec 900
  $sw.Stop()
  $g = [double]$r.eval_duration / 1e9; $p = [double]$r.prompt_eval_duration / 1e9
  [pscustomobject]@{
    total_s = [math]::Round($sw.Elapsed.TotalSeconds, 1)
    prompt_tok = $r.prompt_eval_count; prompt_tok_s = $(if ($p -gt 0) { [math]::Round($r.prompt_eval_count / $p, 1) })
    gen_tok = $r.eval_count; gen_tok_s = $(if ($g -gt 0) { [math]::Round($r.eval_count / $g, 2) })
  }
}

function Rodar($rotulo, $base) {
  Write-Output "=== $rotulo ($base) ==="
  $null = Invoke-Gen $base 'ola' 4   # carrega o modelo
  $a = Invoke-Gen $base $curto 160
  Write-Output ("[geracao] {0} tok -> {1} tok/s" -f $a.gen_tok, $a.gen_tok_s)
  $b = Invoke-Gen $base $longo 24
  Write-Output ("[prefill] {0} tok de prompt a {1} tok/s (total {2}s)" -f $b.prompt_tok, $b.prompt_tok_s, $b.total_s)
}

try {
  Rodar 'CPU (servidor padrao)' 'http://127.0.0.1:11434'
  & $ollama ps | Out-String
  $null = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/generate' -Method Post -Body (@{ model = $Modelo; keep_alive = 0 } | ConvertTo-Json) -ContentType 'application/json'

  $env:OLLAMA_HOST = '127.0.0.1:11435'; $env:OLLAMA_IGPU_ENABLE = '1'
  $p = Start-Process -FilePath $ollama -ArgumentList 'serve' -PassThru -WindowStyle Hidden -RedirectStandardOutput (Join-Path $tmp 'out.txt') -RedirectStandardError (Join-Path $tmp 'err.txt')
  try {
    $ok = $false
    for ($i = 0; $i -lt 60; $i++) { Start-Sleep -Seconds 1; try { $null = Invoke-RestMethod 'http://127.0.0.1:11435/api/version' -TimeoutSec 2; $ok = $true; break } catch {} }
    if (-not $ok) { throw 'servidor temporario nao subiu' }
    Rodar 'iGPU Vulkan (OLLAMA_IGPU_ENABLE=1)' 'http://127.0.0.1:11435'
    & $ollama ps | Out-String
  }
  finally {
    taskkill /PID $($p.Id) /T /F | Out-Null
    Remove-Item Env:OLLAMA_HOST, Env:OLLAMA_IGPU_ENABLE -ErrorAction SilentlyContinue
  }
}
finally { Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue }
