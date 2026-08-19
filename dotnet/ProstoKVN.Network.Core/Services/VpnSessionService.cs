using System.Diagnostics;
using System.Net;
using System.Net.NetworkInformation;
using System.Net.Sockets;
using System.Text.Json;
using System.Text.Json.Nodes;
using ProstoKVN.Network.Core.Models;

namespace ProstoKVN.Network.Core.Services;

public sealed class VpnSessionService(
    SettingsService settingsService,
    RoutingConfigService routingConfigService,
    XrayConfigService xrayConfigService) : IAsyncDisposable
{
    private readonly SemaphoreSlim _lifecycleLock = new(1, 1);
    private Process? _singBoxProcess;
    private Process? _xrayProcess;

    public event Action<string>? Log;
    public bool IsRunning => _singBoxProcess is { HasExited: false }
        && (_activeNode?.Protocol != "vless" || _xrayProcess is { HasExited: false });
    public NodeModel? ActiveNode => _activeNode;
    private NodeModel? _activeNode;

    public async Task StartAsync(
        NodeModel node,
        CorePaths cores,
        AppSettings settings,
        IReadOnlyList<string>? blocklistPaths = null,
        CancellationToken cancellationToken = default)
    {
        await _lifecycleLock.WaitAsync(cancellationToken);
        try
        {
            if (IsRunning && ReferenceEquals(_activeNode, node)) return;
            await StopLockedAsync();

            if (!cores.HasSingBox) throw new FileNotFoundException("Не найден sing-box.exe");
            if (node.Protocol == "vless" && !cores.HasXray) throw new FileNotFoundException("Для VLESS не найден xray.exe");

            Directory.CreateDirectory(settingsService.RuntimeDirectory);
            var tunConfigPath = Path.Combine(settingsService.RuntimeDirectory, "active_tun.json");
            var tunLogPath = Path.Combine(settingsService.RuntimeDirectory, "active_tun.log");
            var xrayConfigPath = Path.Combine(settingsService.RuntimeDirectory, "active_xray.json");
            var xrayLogPath = Path.Combine(settingsService.RuntimeDirectory, "active_xray.log");

            TryDelete(tunConfigPath);
            TryDelete(xrayConfigPath);
            TryDelete(tunLogPath);
            TryDelete(xrayLogPath);

            JsonObject? proxyOverride = null;
            if (node.Protocol.Equals("vless", StringComparison.OrdinalIgnoreCase))
            {
                var port = FindFreePort();
                var xrayConfig = xrayConfigService.BuildSocksBridge(node, port, xrayLogPath);
                await WriteJsonAsync(xrayConfigPath, xrayConfig, cancellationToken);
                Log?.Invoke($"[XRAY] Запуск локального моста на 127.0.0.1:{port}");
                _xrayProcess = StartHidden(cores.Xray!, $"run -c \"{xrayConfigPath}\"");
                if (!await WaitForPortAsync(port, _xrayProcess, TimeSpan.FromSeconds(7), cancellationToken))
                    throw new InvalidOperationException("Xray не поднял локальный SOCKS-мост. " + ReadTail(xrayLogPath));

                proxyOverride = new JsonObject
                {
                    ["type"] = "socks",
                    ["tag"] = "proxy",
                    ["server"] = "127.0.0.1",
                    ["server_port"] = port,
                    ["version"] = "5",
                };
            }

            var tunConfig = routingConfigService.BuildTunConfig(node, tunLogPath, settings, proxyOverride, blocklistPaths);
            await WriteJsonAsync(tunConfigPath, tunConfig, cancellationToken);

            var check = await RunCaptureAsync(cores.SingBox!, $"check -c \"{tunConfigPath}\"", TimeSpan.FromSeconds(12), cancellationToken);
            if (check.ExitCode != 0)
                throw new InvalidOperationException("sing-box отклонил конфигурацию: " + Trim(check.StdErr + Environment.NewLine + check.StdOut, 1800));

            Log?.Invoke($"[VPN] Запуск: {node.Name}");
            _singBoxProcess = StartHidden(cores.SingBox!, $"run -c \"{tunConfigPath}\"");
            _activeNode = node;

            var started = DateTime.UtcNow;
            while (DateTime.UtcNow - started < TimeSpan.FromSeconds(9))
            {
                cancellationToken.ThrowIfCancellationRequested();
                if (_singBoxProcess.HasExited)
                    throw new InvalidOperationException("TUN завершился при запуске. " + ReadTail(tunLogPath));
                if (node.Protocol == "vless" && _xrayProcess is { HasExited: true })
                    throw new InvalidOperationException("Xray завершился при запуске. " + ReadTail(xrayLogPath));
                if (InterfaceExists("prostokvn_network_tun"))
                {
                    Log?.Invoke($"[VPN] Запущен: {node.Name}");
                    return;
                }
                await Task.Delay(250, cancellationToken);
            }

            if (!IsRunning) throw new InvalidOperationException("VPN-процессы завершились при запуске");
            Log?.Invoke("[VPN] TUN-процесс работает, но интерфейс ещё не появился в списке адаптеров");
        }
        catch
        {
            await StopLockedAsync();
            throw;
        }
        finally
        {
            _lifecycleLock.Release();
        }
    }

    public async Task StopAsync(CancellationToken cancellationToken = default)
    {
        await _lifecycleLock.WaitAsync(cancellationToken);
        try { await StopLockedAsync(); }
        finally { _lifecycleLock.Release(); }
    }

    private async Task StopLockedAsync()
    {
        var hadSession = _singBoxProcess is not null || _xrayProcess is not null;
        await StopProcessTreeAsync(_singBoxProcess);
        await StopProcessTreeAsync(_xrayProcess);
        _singBoxProcess?.Dispose();
        _xrayProcess?.Dispose();
        _singBoxProcess = null;
        _xrayProcess = null;
        _activeNode = null;
        if (hadSession) Log?.Invoke("[VPN] Остановлен");
    }

    private static Process StartHidden(string fileName, string arguments)
    {
        var process = new Process
        {
            StartInfo = new ProcessStartInfo
            {
                FileName = fileName,
                Arguments = arguments,
                UseShellExecute = false,
                CreateNoWindow = true,
                WindowStyle = ProcessWindowStyle.Hidden,
                WorkingDirectory = Path.GetDirectoryName(fileName) ?? AppContext.BaseDirectory,
            },
            EnableRaisingEvents = true,
        };
        if (!process.Start()) throw new InvalidOperationException($"Не удалось запустить {Path.GetFileName(fileName)}");
        return process;
    }

    private static async Task<(int ExitCode, string StdOut, string StdErr)> RunCaptureAsync(
        string fileName,
        string arguments,
        TimeSpan timeout,
        CancellationToken cancellationToken)
    {
        using var process = new Process
        {
            StartInfo = new ProcessStartInfo
            {
                FileName = fileName,
                Arguments = arguments,
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                WorkingDirectory = Path.GetDirectoryName(fileName) ?? AppContext.BaseDirectory,
            },
        };
        process.Start();
        var stdoutTask = process.StandardOutput.ReadToEndAsync(cancellationToken);
        var stderrTask = process.StandardError.ReadToEndAsync(cancellationToken);
        using var timeoutCts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        timeoutCts.CancelAfter(timeout);
        try { await process.WaitForExitAsync(timeoutCts.Token); }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            try { process.Kill(true); } catch { }
            throw new TimeoutException($"{Path.GetFileName(fileName)} не завершил проверку за {timeout.TotalSeconds:0} сек.");
        }
        return (process.ExitCode, await stdoutTask, await stderrTask);
    }

    private static async Task<bool> WaitForPortAsync(int port, Process process, TimeSpan timeout, CancellationToken cancellationToken)
    {
        var end = DateTime.UtcNow + timeout;
        while (DateTime.UtcNow < end)
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (process.HasExited) return false;
            try
            {
                using var client = new TcpClient();
                await client.ConnectAsync(IPAddress.Loopback, port, cancellationToken);
                return true;
            }
            catch
            {
                await Task.Delay(100, cancellationToken);
            }
        }
        return false;
    }

    private static int FindFreePort()
    {
        var listener = new TcpListener(IPAddress.Loopback, 0);
        listener.Start();
        var port = ((IPEndPoint)listener.LocalEndpoint).Port;
        listener.Stop();
        return port;
    }

    private static bool InterfaceExists(string name)
    {
        try
        {
            return NetworkInterface.GetAllNetworkInterfaces().Any(x =>
                x.Name.Contains(name, StringComparison.OrdinalIgnoreCase)
                || x.Description.Contains(name, StringComparison.OrdinalIgnoreCase));
        }
        catch { return false; }
    }

    private static async Task StopProcessTreeAsync(Process? process)
    {
        if (process is null) return;
        try
        {
            if (!process.HasExited)
            {
                process.Kill(true);
                using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(4));
                try { await process.WaitForExitAsync(cts.Token); } catch { }
            }
        }
        catch { }
    }

    private static async Task WriteJsonAsync(string path, JsonObject value, CancellationToken cancellationToken)
    {
        var text = value.ToJsonString(new JsonSerializerOptions { WriteIndented = true });
        await File.WriteAllTextAsync(path, text + Environment.NewLine, cancellationToken);
    }

    private static string ReadTail(string path)
    {
        try { return Trim(File.ReadAllText(path), 1600); }
        catch { return string.Empty; }
    }

    private static string Trim(string value, int max) => value.Length <= max ? value : value[^max..];
    private static void TryDelete(string path) { try { File.Delete(path); } catch { } }

    public async ValueTask DisposeAsync()
    {
        await StopAsync();
        _lifecycleLock.Dispose();
    }
}
