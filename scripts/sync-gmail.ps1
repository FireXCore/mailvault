param(
    [Parameter(Mandatory = $true)][string]$Account,
    [Parameter(Mandatory = $true)][string]$Destination
)

$ErrorActionPreference = "Stop"

mailvault sync `
  --account $Account `
  --host imap.gmail.com `
  --provider gmail `
  --auth app-password `
  --destination $Destination `
  --scope all `
  --soft-cap 1GiB `
  --hard-cap 1.25GiB
