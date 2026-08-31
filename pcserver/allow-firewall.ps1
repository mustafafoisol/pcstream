# Run once, as Administrator, so your phone can reach the server on the LAN.
# Only opens the port for Private networks (home/office), not Public.
$port = 8765
New-NetFirewallRule -DisplayName "PCStream $port" `
  -Direction Inbound -Action Allow -Protocol TCP -LocalPort $port `
  -Profile Private | Out-Null
Write-Host "Opened TCP $port on Private networks."
Write-Host "To undo: Remove-NetFirewallRule -DisplayName 'PCStream $port'"
