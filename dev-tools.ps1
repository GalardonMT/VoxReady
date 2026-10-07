# Script de Utilidades para Pruebas Locales y Visualización de Logs en Vivo
param (
    [string]$Action = "menu"
)

function Show-Menu {
    Clear-Host
    Write-Host "==========================================================" -ForegroundColor Cyan
    Write-Host "       VOXREADY - ENTORNO DE PRUEBAS Y LOGS EN VIVO       " -ForegroundColor Yellow
    Write-Host "==========================================================" -ForegroundColor Cyan
    Write-Host " 1. Iniciar Docker + Azure SQL (http://localhost:3000)" -ForegroundColor Green
    Write-Host " 2. Ver Logs en Vivo del Worker (ca-analysis-worker)" -ForegroundColor Magenta
    Write-Host " 3. Ver Logs en Vivo del Backend API (ca-backend-api)" -ForegroundColor Blue
    Write-Host " 4. Ver Logs en Vivo de Visión (ca-vision-service)" -ForegroundColor DarkYellow
    Write-Host " 5. Verificar Azure SQL desde Docker" -ForegroundColor Green
    Write-Host " 6. Ejecutar pruebas desde Docker" -ForegroundColor Green
    Write-Host " 7. Salir" -ForegroundColor Gray
    Write-Host "==========================================================" -ForegroundColor Cyan
    $choice = Read-Host "Seleccione una opción [1-7]"

    switch ($choice) {
        "1" { Start-Frontend }
        "2" { Stream-Worker-Logs }
        "3" { Stream-Backend-Logs }
        "4" { Stream-Vision-Logs }
        "5" { & "$PSScriptRoot\docker.ps1" verify }
        "6" { & "$PSScriptRoot\docker.ps1" test }
        "7" { exit }
        default { Write-Host "Opción inválida."; Start-Sleep -Seconds 1; Show-Menu }
    }
}

function Start-Frontend {
    Write-Host "`nIniciando contenedores conectados a Azure SQL..." -ForegroundColor Green
    & "$PSScriptRoot\docker.ps1" up
}

function Stream-Worker-Logs {
    Write-Host "`nConectando a logs del Worker en Azure (ca-analysis-worker)..." -ForegroundColor Magenta
    Write-Host "Presione Ctrl+C para detener el seguimiento de logs.`n" -ForegroundColor Gray
    az containerapp logs show --name ca-analysis-worker --resource-group rg-voxready-dev --follow
}

function Stream-Backend-Logs {
    Write-Host "`nConectando a logs del Backend API en Azure (ca-backend-api)..." -ForegroundColor Blue
    Write-Host "Presione Ctrl+C para detener el seguimiento de logs.`n" -ForegroundColor Gray
    az containerapp logs show --name ca-backend-api --resource-group rg-voxready-dev --follow
}

function Stream-Vision-Logs {
    Write-Host "`nConectando a logs del Servicio de Visión en Azure (ca-vision-service)..." -ForegroundColor DarkYellow
    Write-Host "Presione Ctrl+C para detener el seguimiento de logs.`n" -ForegroundColor Gray
    az containerapp logs show --name ca-vision-service --resource-group rg-voxready-dev --follow
}

switch ($Action.ToLower()) {
    "frontend" { Start-Frontend }
    "azure"    { Start-Frontend }
    "verify"   { & "$PSScriptRoot\docker.ps1" verify }
    "test"     { & "$PSScriptRoot\docker.ps1" test }
    "worker"   { Stream-Worker-Logs }
    "backend"  { Stream-Backend-Logs }
    "vision"   { Stream-Vision-Logs }
    default    { Show-Menu }
}
