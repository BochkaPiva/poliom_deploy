# PowerShell скрипт развертывания системы ПОЛИОМ на Windows Server

param(
    [string]$Domain = "localhost",
    [string]$InstallPath = "C:\poliom"
)

Write-Host "🚀 Начинаем развертывание системы ПОЛИОМ на Windows Server..." -ForegroundColor Green

# Проверка прав администратора
if (-NOT ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Host "❌ Этот скрипт должен запускаться с правами администратора" -ForegroundColor Red
    exit 1
}

# Проверка наличия Docker Desktop
try {
    docker --version | Out-Null
    Write-Host "✅ Docker найден" -ForegroundColor Green
} catch {
    Write-Host "❌ Docker не найден. Установите Docker Desktop для Windows" -ForegroundColor Red
    Write-Host "Скачайте с: https://www.docker.com/products/docker-desktop" -ForegroundColor Yellow
    exit 1
}

# Создание директорий
Write-Host "📁 Создание директорий..." -ForegroundColor Yellow
$directories = @(
    "$InstallPath\logs",
    "$InstallPath\uploads", 
    "$InstallPath\backups",
    "$InstallPath\nginx\ssl"
)

foreach ($dir in $directories) {
    if (!(Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Host "Создана директория: $dir" -ForegroundColor Gray
    }
}

# Копирование файлов проекта
Write-Host "📋 Копирование файлов проекта..." -ForegroundColor Yellow
if (Test-Path $InstallPath) {
    Copy-Item -Path ".\*" -Destination $InstallPath -Recurse -Force
}

# Настройка переменных окружения
Write-Host "⚙️ Настройка переменных окружения..." -ForegroundColor Yellow
$envFile = "$InstallPath\.env"
if (!(Test-Path $envFile)) {
    Copy-Item -Path "$InstallPath\.env.production" -Destination $envFile
    Write-Host "⚠️ Не забудьте отредактировать файл $envFile" -ForegroundColor Yellow
}

# Генерация самоподписанного SSL сертификата
Write-Host "🔒 Генерация SSL сертификата..." -ForegroundColor Yellow
$certPath = "$InstallPath\nginx\ssl"
if (!(Test-Path "$certPath\privkey.pem")) {
    # Создание самоподписанного сертификата для тестирования
    $cert = New-SelfSignedCertificate -DnsName $Domain -CertStoreLocation "cert:\LocalMachine\My"
    $certPassword = ConvertTo-SecureString -String "poliom123" -Force -AsPlainText
    
    # Экспорт сертификата
    Export-PfxCertificate -Cert $cert -FilePath "$certPath\certificate.pfx" -Password $certPassword | Out-Null
    
    Write-Host "✅ SSL сертификат создан" -ForegroundColor Green
    Write-Host "⚠️ Для продакшена используйте настоящий SSL сертификат" -ForegroundColor Yellow
}

# Создание Windows Service
Write-Host "🔧 Создание Windows Service..." -ForegroundColor Yellow
$serviceName = "PoliomSystem"
$serviceDisplayName = "POLIOM Corporate Bot System"
$serviceDescription = "Корпоративная система чат-бота ПОЛИОМ"

# Создание batch файла для запуска
$startScript = @"
@echo off
cd /d $InstallPath
docker-compose -f docker-compose.prod.yml up -d
"@

$stopScript = @"
@echo off
cd /d $InstallPath
docker-compose -f docker-compose.prod.yml down
"@

$startScript | Out-File -FilePath "$InstallPath\start.bat" -Encoding ASCII
$stopScript | Out-File -FilePath "$InstallPath\stop.bat" -Encoding ASCII

# Создание PowerShell скрипта для управления сервисом
$serviceScript = @"
# Управление сервисом ПОЛИОМ
param([string]`$Action)

switch (`$Action) {
    "start" {
        Set-Location "$InstallPath"
        docker-compose -f docker-compose.prod.yml up -d
    }
    "stop" {
        Set-Location "$InstallPath"
        docker-compose -f docker-compose.prod.yml down
    }
    "restart" {
        Set-Location "$InstallPath"
        docker-compose -f docker-compose.prod.yml down
        docker-compose -f docker-compose.prod.yml up -d
    }
    "status" {
        docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
    }
    default {
        Write-Host "Использование: .\manage.ps1 [start|stop|restart|status]"
    }
}
"@

$serviceScript | Out-File -FilePath "$InstallPath\manage.ps1" -Encoding UTF8

# Создание скрипта резервного копирования
Write-Host "💾 Создание скрипта резервного копирования..." -ForegroundColor Yellow
$backupScript = @"
# Скрипт резервного копирования ПОЛИОМ
`$BackupDir = "$InstallPath\backups"
`$Date = Get-Date -Format "yyyyMMdd_HHmmss"

# Создание резервной копии базы данных
Write-Host "Создание резервной копии базы данных..."
docker exec poliom_postgres pg_dump -U poliom_user poliom_production > "`$BackupDir\db_backup_`$Date.sql"

# Архивирование загруженных файлов
Write-Host "Архивирование файлов..."
Compress-Archive -Path "$InstallPath\uploads\*" -DestinationPath "`$BackupDir\uploads_backup_`$Date.zip" -Force

# Удаление старых резервных копий (старше 30 дней)
Write-Host "Очистка старых резервных копий..."
Get-ChildItem "`$BackupDir\*.sql" | Where-Object {`$_.LastWriteTime -lt (Get-Date).AddDays(-30)} | Remove-Item
Get-ChildItem "`$BackupDir\*.zip" | Where-Object {`$_.LastWriteTime -lt (Get-Date).AddDays(-30)} | Remove-Item

Write-Host "✅ Резервная копия создана: `$Date" -ForegroundColor Green
"@

$backupScript | Out-File -FilePath "$InstallPath\backup.ps1" -Encoding UTF8

# Создание задачи в планировщике для резервного копирования
Write-Host "⏰ Настройка автоматического резервного копирования..." -ForegroundColor Yellow
$taskName = "PoliomBackup"
$taskAction = New-ScheduledTaskAction -Execute "PowerShell.exe" -Argument "-File `"$InstallPath\backup.ps1`""
$taskTrigger = New-ScheduledTaskTrigger -Daily -At "02:00"
$taskSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

try {
    Register-ScheduledTask -TaskName $taskName -Action $taskAction -Trigger $taskTrigger -Settings $taskSettings -Force | Out-Null
    Write-Host "✅ Задача резервного копирования создана" -ForegroundColor Green
} catch {
    Write-Host "⚠️ Не удалось создать задачу резервного копирования: $($_.Exception.Message)" -ForegroundColor Yellow
}

# Настройка Windows Firewall
Write-Host "🔥 Настройка Windows Firewall..." -ForegroundColor Yellow
try {
    New-NetFirewallRule -DisplayName "POLIOM HTTP" -Direction Inbound -Protocol TCP -LocalPort 80 -Action Allow | Out-Null
    New-NetFirewallRule -DisplayName "POLIOM HTTPS" -Direction Inbound -Protocol TCP -LocalPort 443 -Action Allow | Out-Null
    Write-Host "✅ Правила файрвола созданы" -ForegroundColor Green
} catch {
    Write-Host "⚠️ Не удалось настроить файрвол: $($_.Exception.Message)" -ForegroundColor Yellow
}

# Запуск системы
Write-Host "🎯 Запуск системы..." -ForegroundColor Yellow
Set-Location $InstallPath
try {
    & docker-compose -f docker-compose.prod.yml up -d
    Write-Host "✅ Система запущена" -ForegroundColor Green
} catch {
    Write-Host "❌ Ошибка запуска: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ""
Write-Host "✅ Развертывание завершено!" -ForegroundColor Green
Write-Host ""
Write-Host "📋 Следующие шаги:" -ForegroundColor Yellow
Write-Host "1. Отредактируйте файл $InstallPath\.env"
Write-Host "2. Настройте SSL сертификат в $InstallPath\nginx\ssl\"
Write-Host "3. Обновите домен в $InstallPath\nginx\nginx.conf"
Write-Host "4. Перезапустите систему: .\manage.ps1 restart"
Write-Host ""
Write-Host "🌐 Админ-панель будет доступна по адресу: https://$Domain" -ForegroundColor Cyan
Write-Host "📊 Управление: .\manage.ps1 [start|stop|restart|status]" -ForegroundColor Cyan
Write-Host "💾 Резервное копирование: .\backup.ps1" -ForegroundColor Cyan 