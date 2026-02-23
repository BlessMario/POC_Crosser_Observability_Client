param(
    [string]$BaseUrl = "http://127.0.0.1:8000/v1",
    [string]$Node = "mosquitto-test",
    [string]$TopicFilter = "test/#",
    [string]$PublishTopic = "test/copilot/smoke",
    [string]$BrokerHost = "test.mosquitto.org",
    [int]$BrokerPort = 1883,
    [string]$ApiContainerName = "poc_crosser_observability_client-api-1",
    [switch]$PublishToLocalHiveMq,
    [int]$RecordSeconds = 10,
    [int]$PublishCount = 35,
    [int]$MessageLimit = 50
)

$ErrorActionPreference = "Stop"

$createBody = @{
    node = $Node
    topic_filters = @($TopicFilter)
} | ConvertTo-Json -Compress

$sessions = Invoke-RestMethod -Method Get -Uri "$BaseUrl/sessions"
$running = @($sessions | Where-Object { $_.state -eq "RECORDING" })
if ($running.Count -gt 0) {
    $ids = ($running | ForEach-Object { $_.id }) -join ", "
    throw "Recorder already running for session(s): $ids. Stop them first or run a single recorder at a time."
}

if ($PublishToLocalHiveMq) {
    $BrokerHost = "hivemq"
    $BrokerPort = 1883
}

$session = Invoke-RestMethod -Method Post -Uri "$BaseUrl/sessions" -ContentType "application/json" -Body $createBody
$sessionId = $session.id

Write-Output "Created session: $sessionId"
Write-Output "Starting recording on topic filter: $TopicFilter"
Invoke-RestMethod -Method Post -Uri "$BaseUrl/sessions/$sessionId/record/start" | Out-Null

$publisher = Start-Job -ScriptBlock {
    param($ContainerName, $BrokerHostname, $BrokerTcpPort, $Topic, $SessionId, $Count)

    Start-Sleep -Seconds 2
    for ($i = 1; $i -le $Count; $i++) {
        $payload = "session=$SessionId;msg=$i;ts=$(Get-Date -Format o)"
        docker exec $ContainerName python -c "import paho.mqtt.client as m; c=m.Client(); c.connect('$BrokerHostname',$BrokerTcpPort,60); c.publish('$Topic', '$payload'); c.disconnect()" | Out-Null
        Start-Sleep -Seconds 1
    }
} -ArgumentList $ApiContainerName, $BrokerHost, $BrokerPort, $PublishTopic, $sessionId, $PublishCount

Write-Output "Recording for $RecordSeconds seconds and publishing $PublishCount messages to $PublishTopic..."
Start-Sleep -Seconds $RecordSeconds

Wait-Job $publisher | Out-Null
Receive-Job $publisher | Out-Null
Remove-Job $publisher | Out-Null

Write-Output "Stopping recording..."
Invoke-RestMethod -Method Post -Uri "$BaseUrl/sessions/$sessionId/record/stop" | Out-Null

$messages = Invoke-RestMethod -Method Get -Uri "$BaseUrl/sessions/$sessionId/messages?limit=$MessageLimit"
$messagesArray = if ($null -eq $messages) { @() } else { @($messages) }
$messageCount = $messagesArray.Count

Write-Output "Session stopped: $sessionId"
Write-Output "Messages recorded: $messageCount"

$matching = @($messagesArray | Where-Object { $_.topic -eq $PublishTopic })
Write-Output "Messages on ${PublishTopic}: $($matching.Count)"

[pscustomobject]@{
    session_id = $sessionId
    topic_filter = $TopicFilter
    publish_topic = $PublishTopic
    record_seconds = $RecordSeconds
    publish_count = $PublishCount
    total_recorded = $messageCount
    recorded_on_publish_topic = $matching.Count
}
