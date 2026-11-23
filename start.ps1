param([ValidateSet('qwen9b', 'qwen4b', 'wizard7b', 'qwen30b')][string]$Model = 'qwen9b')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$previousModel = $env:CHAT_MODEL_KEY
try {
    $env:CHAT_MODEL_KEY = $Model
    & python server.py
    if ($LASTEXITCODE -ne 0) { throw 'Chat server exited with an error.' }
} finally {
    $env:CHAT_MODEL_KEY = $previousModel
}
