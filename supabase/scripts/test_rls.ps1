Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function ConvertFrom-SecureInput([SecureString]$Value) {
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
}

function Invoke-ProjectRequest {
    param(
        [Parameter(Mandatory)][string]$Method,
        [Parameter(Mandatory)][string]$Path,
        [string]$AccessToken,
        [object]$Body,
        [string]$Prefer = 'return=representation'
    )
    $headers = @{ apikey = $script:PublishableKey; Prefer = $Prefer }
    if ($AccessToken) { $headers.Authorization = "Bearer $AccessToken" }
    $parameters = @{
        Method      = $Method
        Uri         = "$($script:ProjectUrl)/rest/v1/$Path"
        Headers     = $headers
        ErrorAction = 'Stop'
    }
    if ($null -ne $Body) {
        $parameters.ContentType = 'application/json'
        $parameters.Body = ConvertTo-Json -InputObject $Body -Depth 8 -Compress
    }
    return Invoke-RestMethod @parameters
}

function Get-TestAccessToken([string]$Email, [SecureString]$Password) {
    $plainPassword = ConvertFrom-SecureInput $Password
    try {
        $response = Invoke-RestMethod `
            -Method Post `
            -Uri "$($script:ProjectUrl)/auth/v1/token?grant_type=password" `
            -Headers @{ apikey = $script:PublishableKey } `
            -ContentType 'application/json' `
            -Body (ConvertTo-Json -Compress @{ email = $Email; password = $plainPassword })
        if (-not $response.access_token) { throw 'Supabase did not return an access token.' }
        return [string]$response.access_token
    }
    finally {
        Remove-Variable plainPassword -ErrorAction SilentlyContinue
    }
}

function Assert-Forbidden([scriptblock]$Action, [string]$Label) {
    try {
        $null = & $Action
        throw "FAIL: $Label was allowed."
    }
    catch {
        $status = $null
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
            $status = [int]$_.Exception.Response.StatusCode
        }
        if ($status -notin @(401, 403)) { throw }
        Write-Host "PASS: $Label is denied (HTTP $status)."
    }
}

$ProjectUrl = (Read-Host 'Supabase project URL').TrimEnd('/')
$PublishableKey = Read-Host 'Supabase publishable key'
$emailA = Read-Host 'Confirmed test account A email'
$passwordA = Read-Host 'Test account A password' -AsSecureString
$emailB = Read-Host 'Confirmed test account B email'
$passwordB = Read-Host 'Test account B password' -AsSecureString
$tokenA = $null
$tokenB = $null
$conversationId = $null
$initialUpdatedAt = $null

try {
    $tokenA = Get-TestAccessToken $emailA $passwordA
    $tokenB = Get-TestAccessToken $emailB $passwordB
    $userA = (Invoke-RestMethod -Method Get -Uri "$ProjectUrl/auth/v1/user" `
        -Headers @{ apikey = $PublishableKey; Authorization = "Bearer $tokenA" }).id
    $userB = (Invoke-RestMethod -Method Get -Uri "$ProjectUrl/auth/v1/user" `
        -Headers @{ apikey = $PublishableKey; Authorization = "Bearer $tokenB" }).id

    $created = Invoke-ProjectRequest -Method Post -Path 'conversations?select=id,updated_at' `
        -AccessToken $tokenA -Body @{ user_id = $userA
            title = 'RLS test conversation' }
    $conversationId = [string]$created[0].id
    $initialUpdatedAt = [DateTimeOffset]::Parse([string]$created[0].updated_at)
    if (-not $conversationId) { throw 'Conversation creation returned no ID.' }
    Write-Host 'PASS: account A created a conversation.'

    $questionId = [guid]::NewGuid().ToString()
    $null = Invoke-ProjectRequest -Method Post `
        -Path 'messages?select=id' -AccessToken $tokenA `
        -Body @{ conversation_id = $conversationId; user_id = $userA
            role = 'user'; content = 'RLS smoke test'; client_request_id = $questionId }
    $ownMessages = Invoke-ProjectRequest -Method Get `
        -Path "messages?select=id&conversation_id=eq.$conversationId" -AccessToken $tokenA
    if (@($ownMessages).Count -ne 1) { throw 'Account A could not read its message.' }
    Write-Host 'PASS: account A can read its message.'

    $afterMessage = Invoke-ProjectRequest -Method Get `
        -Path "conversations?select=updated_at&id=eq.$conversationId" -AccessToken $tokenA
    $messageUpdatedAt = [DateTimeOffset]::Parse([string]$afterMessage[0].updated_at)
    if ($messageUpdatedAt -le $initialUpdatedAt) {
        throw 'Inserting a message did not advance conversations.updated_at.'
    }
    Write-Host 'PASS: message insertion advances conversation activity.'
    Assert-Forbidden {
        Invoke-ProjectRequest -Method Patch `
            -Path "conversations?id=eq.$conversationId" -AccessToken $tokenA `
            -Body @{ updated_at = $initialUpdatedAt.ToString('o') }
    } 'Direct client timestamp update'

    $otherConversation = Invoke-ProjectRequest -Method Get `
        -Path "conversations?select=id&id=eq.$conversationId" -AccessToken $tokenB
    if (@($otherConversation).Count -ne 0) { throw 'Account B read account A conversation.' }
    Write-Host 'PASS: account B cannot read account A conversation.'

    $otherUpdate = Invoke-ProjectRequest -Method Patch `
        -Path "conversations?id=eq.$conversationId&select=id" -AccessToken $tokenB `
        -Body @{ title = 'Unauthorized rename' }
    if (@($otherUpdate).Count -ne 0) { throw 'Account B modified account A conversation.' }
    $ownerCheck = Invoke-ProjectRequest -Method Get `
        -Path "conversations?select=title&id=eq.$conversationId" -AccessToken $tokenA
    if ($ownerCheck[0].title -ne 'RLS test conversation') { throw 'Account B changed the title.' }
    Write-Host 'PASS: account B cannot rename account A conversation.'

    $otherDelete = Invoke-ProjectRequest -Method Delete `
        -Path "conversations?id=eq.$conversationId&select=id" -AccessToken $tokenB
    if (@($otherDelete).Count -ne 0) { throw 'Account B deleted account A conversation.' }
    Write-Host 'PASS: account B cannot delete account A conversation.'

    Assert-Forbidden {
        Invoke-ProjectRequest -Method Post -Path 'messages' -AccessToken $tokenB `
            -Body @{ conversation_id = $conversationId; user_id = $userB; role = 'user'; content = 'cross-account write' }
    } 'Cross-account message insertion'
    Assert-Forbidden {
        Invoke-ProjectRequest -Method Post -Path 'messages' -AccessToken $tokenA `
            -Body @{ conversation_id = $conversationId; user_id = $userA; role = 'assistant'; content = 'forged assistant response' }
    } 'Client-supplied assistant message'
    Assert-Forbidden {
        Invoke-ProjectRequest -Method Patch `
            -Path "messages?conversation_id=eq.$conversationId" -AccessToken $tokenB `
            -Body @{ content = 'unauthorized edit' }
    } 'Cross-account message update'
    $stillOwned = Invoke-ProjectRequest -Method Get `
        -Path "messages?select=content&conversation_id=eq.$conversationId" -AccessToken $tokenA
    if ($stillOwned[0].content -ne 'RLS smoke test') { throw 'Account B edited account A message.' }
    Write-Host 'PASS: account B cannot edit account A messages.'
    Assert-Forbidden {
        Invoke-ProjectRequest -Method Delete `
            -Path "messages?conversation_id=eq.$conversationId" -AccessToken $tokenB
    } 'Cross-account message deletion'
    Assert-Forbidden {
        Invoke-ProjectRequest -Method Delete `
            -Path "messages?conversation_id=eq.$conversationId" -AccessToken $tokenA
    } 'Direct client message deletion'
    $stillPresent = Invoke-ProjectRequest -Method Get `
        -Path "messages?select=id&conversation_id=eq.$conversationId" -AccessToken $tokenA
    if (@($stillPresent).Count -ne 1) { throw 'Account B deleted account A message.' }
    Write-Host 'PASS: account B cannot delete account A messages.'
    Assert-Forbidden {
        Invoke-ProjectRequest -Method Get -Path "conversations?select=id&id=eq.$conversationId"
    } 'Anonymous conversation read'

    $null = Invoke-ProjectRequest -Method Delete `
        -Path "conversations?id=eq.$conversationId&select=id" -AccessToken $tokenA
    $remaining = Invoke-ProjectRequest -Method Get `
        -Path "messages?select=id&conversation_id=eq.$conversationId" -AccessToken $tokenA
    if (@($remaining).Count -ne 0) { throw 'Conversation deletion did not cascade to messages.' }
    $conversationId = $null
    Write-Host 'PASS: account A deleted its conversation and messages.'
}
finally {
    if ($conversationId -and $tokenA) {
        try {
            $null = Invoke-ProjectRequest -Method Delete `
                -Path "conversations?id=eq.$conversationId" -AccessToken $tokenA `
                -Prefer 'return=minimal'
        }
        catch {
            Write-Warning 'Could not clean up the temporary RLS test conversation.'
        }
    }
    Remove-Variable tokenA, tokenB, passwordA, passwordB -ErrorAction SilentlyContinue
    [GC]::Collect()
}
