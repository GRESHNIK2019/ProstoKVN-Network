using System.IO.Compression;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text.Json;

namespace ProstoKVN.Network.Core.Services;

public sealed class CoreInstallerService(SettingsService settingsService, HttpClient? httpClient = null)
{
    private readonly HttpClient _httpClient = httpClient ?? CreateClient();

    public async Task<CorePaths> InstallAsync(
        bool installSingBox = true,
        bool installXray = true,
        IProgress<string>? progress = null,
        CancellationToken cancellationToken = default)
    {
        Directory.CreateDirectory(settingsService.CoresDirectory);
        if (installSingBox)
        {
            progress?.Report("sing-box: получаю последний официальный релиз...");
            var release = await GetLatestReleaseAsync("SagerNet/sing-box", cancellationToken);
            var suffix = RuntimeInformation.ProcessArchitecture == Architecture.Arm64 ? "-windows-arm64.zip" : "-windows-amd64.zip";
            var asset = FindAsset(release, name => name.StartsWith("sing-box-", StringComparison.OrdinalIgnoreCase) && name.EndsWith(suffix, StringComparison.OrdinalIgnoreCase));
            await InstallZipAssetAsync(asset, "sing-box", "sing-box.exe", progress, cancellationToken);
            progress?.Report($"sing-box: установлен ({release.TagName})");
        }

        if (installXray)
        {
            progress?.Report("Xray: получаю последний официальный релиз...");
            var release = await GetLatestReleaseAsync("XTLS/Xray-core", cancellationToken);
            var expected = RuntimeInformation.ProcessArchitecture == Architecture.Arm64
                ? "Xray-windows-arm64-v8a.zip"
                : "Xray-windows-64.zip";
            var asset = FindAsset(release, name => name.Equals(expected, StringComparison.OrdinalIgnoreCase));
            await InstallZipAssetAsync(asset, "xray", "xray.exe", progress, cancellationToken);
            progress?.Report($"Xray: установлен ({release.TagName})");
        }

        return new CoreLocatorService(settingsService).Find();
    }

    private async Task InstallZipAssetAsync(
        ReleaseAsset asset,
        string targetName,
        string exeName,
        IProgress<string>? progress,
        CancellationToken cancellationToken)
    {
        var tempRoot = Path.Combine(Path.GetTempPath(), $"prostokvn-{targetName}-{Guid.NewGuid():N}");
        Directory.CreateDirectory(tempRoot);
        try
        {
            var archive = Path.Combine(tempRoot, asset.Name);
            await DownloadAsync(asset.DownloadUrl, archive, targetName, progress, cancellationToken);
            await VerifyDigestAsync(archive, asset.Digest, cancellationToken);

            var extracted = Path.Combine(tempRoot, "extract");
            ZipFile.ExtractToDirectory(archive, extracted);
            var exe = Directory.EnumerateFiles(extracted, exeName, SearchOption.AllDirectories).FirstOrDefault()
                ?? throw new InvalidOperationException($"В официальном архиве не найден {exeName}");

            var sourceDirectory = Path.GetDirectoryName(exe)!;
            var target = Path.Combine(settingsService.CoresDirectory, targetName);
            var staging = target + ".new";
            var old = target + ".old";
            TryDeleteDirectory(staging);
            CopyDirectory(sourceDirectory, staging);
            TryDeleteDirectory(old);
            if (Directory.Exists(target)) Directory.Move(target, old);
            Directory.Move(staging, target);
            TryDeleteDirectory(old);
        }
        finally
        {
            TryDeleteDirectory(tempRoot);
        }
    }

    private async Task DownloadAsync(string url, string path, string title, IProgress<string>? progress, CancellationToken cancellationToken)
    {
        using var response = await _httpClient.GetAsync(url, HttpCompletionOption.ResponseHeadersRead, cancellationToken);
        response.EnsureSuccessStatusCode();
        var total = response.Content.Headers.ContentLength;
        await using var input = await response.Content.ReadAsStreamAsync(cancellationToken);
        await using var output = File.Create(path);
        var buffer = new byte[256 * 1024];
        long done = 0;
        int count;
        while ((count = await input.ReadAsync(buffer, cancellationToken)) > 0)
        {
            await output.WriteAsync(buffer.AsMemory(0, count), cancellationToken);
            done += count;
            if (total is > 0)
                progress?.Report($"{title}: загрузка {done * 100 / total.Value}%");
        }
    }

    private static async Task VerifyDigestAsync(string path, string? digest, CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(digest) || !digest.StartsWith("sha256:", StringComparison.OrdinalIgnoreCase)) return;
        var expected = digest[(digest.IndexOf(':') + 1)..].Trim();
        await using var stream = File.OpenRead(path);
        var actual = Convert.ToHexString(await SHA256.HashDataAsync(stream, cancellationToken)).ToLowerInvariant();
        if (!actual.Equals(expected, StringComparison.OrdinalIgnoreCase))
            throw new CryptographicException("SHA256 загруженного core не совпадает с GitHub release asset");
    }

    private async Task<ReleaseInfo> GetLatestReleaseAsync(string repository, CancellationToken cancellationToken)
    {
        using var response = await _httpClient.GetAsync($"https://api.github.com/repos/{repository}/releases/latest", cancellationToken);
        response.EnsureSuccessStatusCode();
        await using var stream = await response.Content.ReadAsStreamAsync(cancellationToken);
        using var document = await JsonDocument.ParseAsync(stream, cancellationToken: cancellationToken);
        var root = document.RootElement;
        var assets = new List<ReleaseAsset>();
        foreach (var asset in root.GetProperty("assets").EnumerateArray())
        {
            assets.Add(new ReleaseAsset(
                asset.GetProperty("name").GetString() ?? string.Empty,
                asset.GetProperty("browser_download_url").GetString() ?? string.Empty,
                asset.TryGetProperty("digest", out var digest) ? digest.GetString() : null));
        }
        return new ReleaseInfo(root.GetProperty("tag_name").GetString() ?? "latest", assets);
    }

    private static ReleaseAsset FindAsset(ReleaseInfo release, Func<string, bool> predicate) =>
        release.Assets.FirstOrDefault(x => predicate(x.Name))
        ?? throw new InvalidOperationException("В последнем официальном релизе не найден подходящий Windows-архив");

    private static HttpClient CreateClient()
    {
        var client = new HttpClient { Timeout = TimeSpan.FromMinutes(2) };
        client.DefaultRequestHeaders.UserAgent.ParseAdd("ProstoKVN-Network-CoreBootstrap/2.0");
        client.DefaultRequestHeaders.Accept.ParseAdd("application/vnd.github+json");
        return client;
    }

    private static void CopyDirectory(string source, string destination)
    {
        Directory.CreateDirectory(destination);
        foreach (var file in Directory.EnumerateFiles(source))
            File.Copy(file, Path.Combine(destination, Path.GetFileName(file)), true);
        foreach (var directory in Directory.EnumerateDirectories(source))
            CopyDirectory(directory, Path.Combine(destination, Path.GetFileName(directory)));
    }

    private static void TryDeleteDirectory(string path) { try { if (Directory.Exists(path)) Directory.Delete(path, true); } catch { } }

    private sealed record ReleaseInfo(string TagName, IReadOnlyList<ReleaseAsset> Assets);
    private sealed record ReleaseAsset(string Name, string DownloadUrl, string? Digest);
}
