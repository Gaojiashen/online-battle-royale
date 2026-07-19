# 切换到 DeepSeek 直连模式
$env:ANTHROPIC_BASE_URL="https://api.deepseek.com/anthropic"
$env:ANTHROPIC_AUTH_TOKEN="sk-47d2f43f99e6438fae91516136110e1a"
$env:ANTHROPIC_MODEL="deepseek-v4-pro[1m]"
$env:ANTHROPIC_DEFAULT_OPUS_MODEL="deepseek-v4-pro[1m]"
$env:ANTHROPIC_DEFAULT_SONNET_MODEL="deepseek-v4-pro[1m]"
$env:ANTHROPIC_DEFAULT_HAIKU_MODEL="deepseek-v4-flash"
$env:CLAUDE_CODE_SUBAGENT_MODEL="deepseek-v4-flash"
$env:CLAUDE_CODE_EFFORT_LEVEL="max"

Write-Host "✅ 已切换到 DeepSeek 直连模式" -ForegroundColor Green
Write-Host "当前 ANTHROPIC_BASE_URL = $env:ANTHROPIC_BASE_URL" -ForegroundColor Yellow