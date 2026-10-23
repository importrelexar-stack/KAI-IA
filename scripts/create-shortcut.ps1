<#
.SYNOPSIS
  Crea el acceso directo «KAI AI» en el escritorio (y opcionalmente en el menú Inicio).

.DESCRIPTION
  El acceso abre start.bat con el ícono de KAI. Sólo crea o actualiza su propio acceso directo:
  si ya existe uno «KAI AI» que apunta a otro lado (por ejemplo, el de la app de escritorio
  instalada), no lo pisa y crea «KAI AI (scripts)».

.PARAMETER StartMenu
  También lo agrega al menú Inicio.

.PARAMETER Remove
  Quita los accesos directos creados por este script.
#>
param([switch]$StartMenu, [switch]$Remove)

. "$PSScriptRoot\_common.ps1"

$target = Join-Path $RepoRoot 'start.bat'
$icon = Join-Path $RepoRoot 'apps\desktop\src-tauri\icons\icon.ico'
$shell = New-Object -ComObject WScript.Shell

function Get-Places {
    $places = @([Environment]::GetFolderPath('Desktop'))  # respeta el escritorio redirigido a OneDrive
    if ($StartMenu -or $Remove) { $places += [Environment]::GetFolderPath('Programs') }
    return $places | Where-Object { $_ }
}

function Test-Ours([string]$lnk) {
    if (-not (Test-Path $lnk)) { return $false }
    return ($shell.CreateShortcut($lnk).TargetPath -ieq $target)
}

foreach ($dir in Get-Places) {
    $main = Join-Path $dir 'KAI AI.lnk'
    $alt = Join-Path $dir 'KAI AI (scripts).lnk'
    if ($Remove) {
        foreach ($lnk in @($main, $alt)) {
            if (Test-Ours $lnk) { Remove-Item $lnk -Force; Write-Ok "Quitado: $lnk" }
        }
        continue
    }
    $path = if ((Test-Path $main) -and -not (Test-Ours $main)) { $alt } else { $main }
    $s = $shell.CreateShortcut($path)
    $s.TargetPath = $target
    $s.WorkingDirectory = $RepoRoot
    $s.Description = 'Iniciar KAI AI'
    $s.WindowStyle = 7  # la consola de inicio queda minimizada
    if (Test-Path $icon) { $s.IconLocation = "$icon,0" }
    $s.Save()
    Write-Ok "Acceso directo: $path"
}
