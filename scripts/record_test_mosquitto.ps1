param(
    [string]$BaseUrl = "http://127.0.0.1:8000/v1",
    [string]$Node = "mosquitto-test",
    [string]$TopicFilter = "test/#",
    [int]$RecordSeconds = 10,
    [int]$MessageLimit = 20
)

$ErrorActionPreference = "Stop"

$createBody = @{
    node = $Node
    topic_filters = @($TopicFilter)
} | ConvertTo-Json -Compress

$session = Invoke-RestMethod -Method Post -Uri "$BaseUrl/sessions" -ContentType "application/json" -Body $createBody
$sessionId = $session.id

Write-Output "Created session: $sessionId"
Write-Output "Starting recording on topic filter: $TopicFilter"
Invoke-RestMethod -Method Post -Uri "$BaseUrl/sessions/$sessionId/record/start" | Out-Null

Write-Output "Recording for $RecordSeconds seconds..."
Start-Sleep -Seconds $RecordSeconds

Write-Output "Stopping recording..."
Invoke-RestMethod -Method Post -Uri "$BaseUrl/sessions/$sessionId/record/stop" | Out-Null

$messages = Invoke-RestMethod -Method Get -Uri "$BaseUrl/sessions/$sessionId/messages?limit=$MessageLimit"
$messageCount = if ($null -eq $messages) { 0 } else { @($messages).Count }

$sessionState = Invoke-RestMethod -Method Get -Uri "$BaseUrl/sessions"
$sessionRow = @($sessionState | Where-Object { $_.id -eq $sessionId }) | Select-Object -First 1
$state = if ($null -eq $sessionRow) { "UNKNOWN" } else { $sessionRow.state }

Write-Output "Session closed/stopped: $sessionId"
Write-Output "Final state: $state"
Write-Output "Messages recorded: $messageCount"

[pscustomobject]@{
    session_id = $sessionId
    topic_filter = $TopicFilter
    record_seconds = $RecordSeconds
    final_state = $state
    message_count = $messageCount
}
