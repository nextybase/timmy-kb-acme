$mach = [Environment]::GetEnvironmentVariable('Path',[EnvironmentVariableTarget]::Machine)
$user = [Environment]::GetEnvironmentVariable('Path',[EnvironmentVariableTarget]::User)

Write-Host "Machine PATH entries with quotes:"
$mach -split ';' | Where-Object { $_ -like '*"*' } | ForEach-Object { Write-Host " - $_" }

Write-Host ""
Write-Host "User PATH entries with quotes:"
$user -split ';' | Where-Object { $_ -like '*"*' } | ForEach-Object { Write-Host " - $_" }

Write-Host ""
Write-Host "Effective PATH entries with quotes (current shell):"
$env:Path -split ';' | Where-Object { $_ -like '*"*' } | ForEach-Object { Write-Host " - $_" }

