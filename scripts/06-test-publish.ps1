# Publish test messages.

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\00-config.ps1"

$validMessage = @'
{
  "id": "57b2d226-4e29-4d00-a7cb-663a81d42229",
  "name": "asWWKWUogiEJS",
  "description": "Lorem ipsum praesent elit aenean ultricies pharetra etiam cubilia.",
  "is_in_stock": "false",
  "price": "873.06",
  "last_update": "Mon, 17 Jun 2024 13:47:16 UTC",
  "attributes": [
    { "key": "key-0", "value": "vulputate" },
    { "key": "key-1", "value": "ipsum" },
    { "key": "key-2", "value": "sociosqu" }
  ]
}
'@

# 1. Compress the multiline JSON into a single line safely
$compactMessage = $validMessage | ConvertFrom-Json | ConvertTo-Json -Compress

# 2. Escape the double quotes so Python receives actual quotes, not raw strings
$escapedMessage = $compactMessage -replace '"', '\"'

# 3. Build the EXACT command line string that works natively in standard cmd.exe
# Notice the `" ` around the escaped message to group the spaces together.
$cmdLine = "gcloud pubsub topics publish $TopicName --project=$ProjectId --message=`"$escapedMessage`""

# 4. Write it to a temporary batch script. This "airgaps" PowerShell's quote parser entirely!
$tempScript = "$PSScriptRoot\temp-publish.cmd"
$cmdLine | Set-Content $tempScript -Encoding ASCII

Write-Host "Publishing valid sample message via cmd.exe airgap..." -ForegroundColor Cyan

# 5. Execute the batch script
& $tempScript

# 6. Clean up the temp file so your directory stays clean
Remove-Item $tempScript

# Write-Host "Publishing malformed message (should end up in the DLQ)..." -ForegroundColor Cyan
gcloud pubsub topics publish $TopicName --project=$ProjectId "--message='this is not valid json {'"

Write-Host "Done. Give the function ~30s, then check BigQuery and the function logs:" -ForegroundColor Green
Write-Host "  gcloud functions logs read $FunctionName --project=$ProjectId --region=$Region --gen2 --limit=50"
