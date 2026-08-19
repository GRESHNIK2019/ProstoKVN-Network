using System.Diagnostics;
using System.Net;
using System.Net.Sockets;
using System.Text.Json;
using System.Text.Json.Nodes;
using ProstoKVN.Network.Core.Models;

namespace ProstoKVN.Network.Core.Services;

public sealed class NodeTestService(SettingsService settingsService, XrayConfigService xrayConfigService)
{
    private static readonly (string Host, int Port)[] TcpTargets =
    [
        ("www.gstatic.com", 443),
        ("www.cloudflare.com", 443),
    ];

    public async Task<NodeModel> TestAsync(NodeModel node, CorePaths cores, CancellationToken cancellationToken = default)
    {
        node.LatencyMs = null;
        node.UdpOk = false;
        node.Score = -999999;
        node.IsValid = true;
        node.Error = string.Empty;
        node.TestStatus = "Проверка...";

        if (node.Protocol == "vless" && !cores.HasXray)
        {
            Fail(node, "Для VLESS нужен xray.exe", "Нужен Xray");
            return node;
        }
        if (node.Protocol != "vless" && !cores.HasSingBox)
        {
            Fail(node, "Не найден sing-box.exe", "Нужен sing-box");
            return node;
        }

        Directory.CreateDirectory(settingsService.RuntimeDirectory);
        var port = FindFreePort();
        var token = $"{Environment.ProcessId}_{Environment.CurrentManagedThreadId}_{port}_{Guid.NewGuid():N}";
        var configPath = Path.Combine(settingsService.RuntimeDirectory, $"test_{token}.json");
        var logPath = Path.Combine(settingsService.RuntimeDirectory, $"test_{token}.log");
        Process? process = null;

        try
        {
            if (node.Protocol == "vless")
            {
                var config = xrayConfigService.BuildSocksBridge(node, port, logPath);
                await WriteJsonAsync(configPath, config, cancellationToken);
                process = StartHidden(cores.Xray!, $"run -c \"{configPath}\"");
            }
            else
            {
                var config = BuildSingBoxTestConfig(node, port, logPath);
                await WriteJsonAsync(configPath, config, cancellationToken);
                var check = await RunCaptureAsync(cores.SingBox!, $"check -c \"{configPath}\"", cancellationToken);
                if (check.ExitCode != 0)
                {
                    Fail(node, Trim(check.StdErr + Environment.NewLine + check.StdOut, 1000), "Конфиг не поддержан");
                    return node;
                }
                process = StartHidden(cores.SingBox!, $"run -c \"{configPath}\"");
            }

            if (!await WaitForPortAsync(port, process, TimeSpan.FromSeconds(6), cancellationToken))
            {
                Fail(node, "Тестовое ядро не подняло SOCKS. " + ReadTail(logPath), "Не запустился");
                return node;
            }

            var https = new List<double>();
            for (var attempt = 0; attempt < 3; attempt++)
            {
                var latency = await Socks5Probe.MeasureHttpsAsync(port, TimeSpan.FromSeconds(4), cancellationToken);
                if (latency is not null) https.Add(latency.Value);
            }

            var tcpOk = 0;
            foreach (var target in TcpTargets)
            {
                if (await Socks5Probe.TestConnectAsync(port, target.Host, target.Port, TimeSpan.FromSeconds(3), cancellationToken)) tcpOk++;
            }

            node.UdpOk = await Socks5Probe.TestUdpDnsAsync(port, TimeSpan.FromSeconds(3), cancellationToken);
            node.LatencyMs = https.Count > 0 ? Median(https) : null;
            ApplyScore(node, https.Count, tcpOk, TcpTargets.Length);
            node.IsValid = https.Count > 0;
            node.Error = node.IsValid ? string.Empty : ReadTail(logPath);
            return node;
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            node.TestStatus = "Отменено";
            throw;
        }
        catch (Exception ex)
        {
            Fail(node, ex.Message, "Ошибка");
            return node;
        }
        finally
        {
            await StopProcessAsync(process);
            TryDelete(configPath);
            if (node.IsValid && node.LatencyMs is not null) TryDelete(logPath);
        }
    }

    private static JsonObject BuildSingBoxTestConfig(NodeModel node, int port, string logPath)
    {
        var outbound = node.Outbound.DeepClone().AsObject();
        outbound["tag"] = "proxy";
        return new JsonObject
        {
            ["log"] = new JsonObject { ["level"] = "error", ["timestamp"] = true, ["output"] = logPath },
            ["inbounds"] = new JsonArray(new JsonObject
            {
                ["type"] = "socks",
                ["tag"] = "test-in",
                ["listen"] = "127.0.0.1",
                ["listen_port"] = port,
            }),
            ["outbounds"] = new JsonArray(outbound, new JsonObject { ["type"] = "direct", ["tag"] = "direct" }),
            ["route"] = new JsonObject
            {
                ["auto_detect_interface"] = true,
                ["rules"] = new JsonArray(new JsonObject
                {
                    ["inbound"] = new JsonArray("test-in"),
                    ["action"] = "route",
                    ["outbound"] = "proxy",
                }),
                ["final"] = "direct",
            },
        };
    }

    private static void ApplyScore(NodeModel node, int httpsSuccess, int tcpOk, int tcpTotal)
    {
        var stability = httpsSuccess / 3.0;
        var tcpRatio = tcpTotal == 0 ? 0.0 : (double)tcpOk / tcpTotal;
        var score = stability * 600 + tcpRatio * 200;
        if (node.UdpOk) score += 180;
        if (node.LatencyMs is not null) score += Math.Max(0, 320 - Math.Min(node.LatencyMs.Value, 1600) * 0.20);
        else score -= 600;
        node.Score = score;

        node.TestStatus = httpsSuccess switch
        {
            3 when node.UdpOk => "OK 3/3",
            >= 2 => $"Стабильно {httpsSuccess}/3" + (node.UdpOk ? string.Empty : " · без UDP"),
            1 => "Нестабильно 1/3",
            _ => "HTTPS недоступен",
        };
    }

    private static void Fail(NodeModel node, string error, string status)
    {
        node.IsValid = false;
        node.Score = -5000;
        node.Error = error;
        node.TestStatus = status;
    }

    private static double Median(List<double> values)
    {
        values.Sort();
        return values.Count % 2 == 1
            ? values[values.Count / 2]
            : (values[values.Count / 2 - 1] + values[values.Count / 2]) / 2;
    }

    private static int FindFreePort()
    {
        var listener = new TcpListener(IPAddress.Loopback, 0);
        listener.Start();
        var port = ((IPEndPoint)listener.LocalEndpoint).Port;
        listener.Stop();
        return port;
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
                WorkingDirectory = Path.GetDirectoryName(fileName) ?? AppContext.BaseDirectory,
            },
        };
        process.Start();
        return process;
    }

    private static async Task<(int ExitCode, string StdOut, string StdErr)> RunCaptureAsync(string fileName, string arguments, CancellationToken cancellationToken)
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
        var stdout = process.StandardOutput.ReadToEndAsync(cancellationToken);
        var stderr = process.StandardError.ReadToEndAsync(cancellationToken);
        using var cts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        cts.CancelAfter(TimeSpan.FromSeconds(10));
        await process.WaitForExitAsync(cts.Token);
        return (process.ExitCode, await stdout, await stderr);
    }

    private static async Task<bool> WaitForPortAsync(int port, Process process, TimeSpan timeout, CancellationToken cancellationToken)
    {
        var end = DateTime.UtcNow + timeout;
        while (DateTime.UtcNow < end)
        {
            if (process.HasExited) return false;
            try
            {
                using var client = new TcpClient();
                await client.ConnectAsync(IPAddress.Loopback, port, cancellationToken);
                return true;
            }
            catch { await Task.Delay(90, cancellationToken); }
        }
        return false;
    }

    private static async Task StopProcessAsync(Process? process)
    {
        if (process is null) return;
        try
        {
            if (!process.HasExited)
            {
                process.Kill(true);
                using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(3));
                try { await process.WaitForExitAsync(cts.Token); } catch { }
            }
        }
        catch { }
        finally { process.Dispose(); }
    }

    private static async Task WriteJsonAsync(string path, JsonObject value, CancellationToken cancellationToken) =>
        await File.WriteAllTextAsync(path, value.ToJsonString(new JsonSerializerOptions { WriteIndented = true }) + Environment.NewLine, cancellationToken);

    private static string ReadTail(string path) { try { return Trim(File.ReadAllText(path), 1000); } catch { return string.Empty; } }
    private static string Trim(string value, int max) => value.Length <= max ? value : value[^max..];
    private static void TryDelete(string path) { try { File.Delete(path); } catch { } }
}
