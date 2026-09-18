param([Parameter(Mandatory=$true)][string]$ContactId,[Parameter(Mandatory=$true)][string]$ScenarioId,[Parameter(Mandatory=$true)][string]$AgentId)
$ErrorActionPreference = 'Stop'
$credential = Get-Credential -UserName 'admin' -Message 'AI Caller local administrator'
$login = @{username=$credential.UserName;password=$credential.GetNetworkCredential().Password} | ConvertTo-Json
Invoke-RestMethod -Uri 'http://localhost:3000/api/auth/login' -Method Post -ContentType 'application/json' -Body $login -SessionVariable callerSession | Out-Null
$login = $null
$csrf = $callerSession.Cookies.GetCookies([uri]'http://localhost:3000')['csrf'].Value
$body = @{contact_id=$ContactId;scenario_id=$ScenarioId;agent_id=$AgentId} | ConvertTo-Json
Invoke-RestMethod -Uri 'http://localhost:3000/api/test-call' -Method Post -ContentType 'application/json' -Headers @{'X-CSRF-Token'=$csrf} -Body $body -WebSession $callerSession
