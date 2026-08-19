using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace ProstoKVN.Network.Core.Services;

public sealed class BlocklistService(SettingsService settingsService, HttpClient? httpClient = null)
{
    private static readonly string[][] DomainSources =
    [
        [
            "https://raw.githubusercontent.com/itdoginfo/allow-domains/main/Russia/inside-raw.lst",
            "https://cdn.jsdelivr.net/gh/itdoginfo/allow-domains@main/Russia/inside-raw.lst",
        ],
        [
            "https://raw.githubusercontent.com/runetfreedom/russia-blocked-geosite/release/ru-blocked.txt",
            "https://cdn.jsdelivr.net/gh/runetfreedom/russia-blocked-geosite@release/ru-blocked.txt",
        ],
    ];

    private static readonly Dictionary<string, string[]> ServiceSources = new(StringComparer.OrdinalIgnoreCase)
    {
        ["youtube"] =
        [
            "https://raw.githubusercontent.com/itdoginfo/allow-domains/main/Services/youtube.lst",
            "https://cdn.jsdelivr.net/gh/itdoginfo/allow-domains@main/Services/youtube.lst",
        ],
        ["discord"] =
        [
            "https://raw.githubusercontent.com/itdoginfo/allow-domains/main/Services/discord.lst",
            "https://cdn.jsdelivr.net/gh/itdoginfo/allow-domains@main/Services/discord.lst",
        ],
        ["meta"] =
        [
            "https://raw.githubusercontent.com/itdoginfo/allow-domains/main/Services/meta.lst",
            "https://cdn.jsdelivr.net/gh/itdoginfo/allow-domains@main/Services/meta.lst",
        ],
        ["twitter"] =
        [
            "https://raw.githubusercontent.com/itdoginfo/allow-domains/main/Services/twitter.lst",
            "https://cdn.jsdelivr.net/gh/itdoginfo/allow-domains@main/Services/twitter.lst",
        ],
        ["tiktok"] =
        [
            "https://raw.githubusercontent.com/itdoginfo/allow-domains/main/Services/tiktok.lst",
            "https://cdn.jsdelivr.net/gh/itdoginfo/allow-domains@main/Services/tiktok.lst",
        ],
        ["telegram"] =
        [
            "https://raw.githubusercontent.com/itdoginfo/allow-domains/main/Services/telegram.lst",
            "https://cdn.jsdelivr.net/gh/itdoginfo/allow-domains@main/Services/telegram.lst",
        ],
    };

    private static readonly Dictionary<string, string[]> IpSources = new(StringComparer.OrdinalIgnoreCase)
    {
        ["ru_blocked_ip"] =
        [
            "https://raw.githubusercontent.com/runetfreedom/russia-blocked-geoip/release/srs/ru-blocked.srs",
            "https://cdn.jsdelivr.net/gh/runetfreedom/russia-blocked-geoip@release/srs/ru-blocked.srs",
        ],
        ["ru_blocked_community_ip"] =
        [
            "https://raw.githubusercontent.com/runetfreedom/russia-blocked-geoip/release/srs/ru-blocked-community.srs",
            "https://cdn.jsdelivr.net/gh/runetfreedom/russia-blocked-geoip@release/srs/ru-blocked-community.srs",
        ],
        ["re_filter_ip"] =
        [
            "https://raw.githubusercontent.com/runetfreedom/russia-blocked-geoip/release/srs/re-filter.srs",
            "https://cdn.jsdelivr.net/gh/runetfreedom/russia-blocked-geoip@release/srs/re-filter.srs",
        ],
    };

    private const string YouTubeFallback = """
        youtube.com
        ytimg.com
        yting.com
        ggpht.com
        googlevideo.com
        youtubekids.com
        youtu.be
        yt.be
        youtube-nocookie.com
        wide-youtube.l.google.com
        ytimg.l.google.com
        youtubei.googleapis.com
        youtubeembeddedplayer.googleapis.com
        youtube-ui.l.google.com
        yt-video-upload.l.google.com
        jnn-pa.googleapis.com
        yt3.googleusercontent.com
        """;

    private readonly HttpClient _httpClient = httpClient ?? CreateClient();

    public string DirectoryPath => Path.Combine(settingsService.BaseDirectory, "blocklists");
    public string MetaPath => Path.Combine(DirectoryPath, "meta.json");

    public IReadOnlyList<string> GetCachedPaths()
    {
        var candidates = new List<string>
        {
            Path.Combine(DirectoryPath, "ru_domains.json"),
            Path.Combine(DirectoryPath, "service_domains.json"),
        };
        candidates.AddRange(IpSources.Keys.Select(name => Path.Combine(DirectoryPath, name + ".srs")));
        return candidates.Where(path => File.Exists(path) && new FileInfo(path).Length > 0).ToArray();
    }

    public async Task<TimeSpan?> GetAgeAsync(CancellationToken cancellationToken = default)
    {
        try
        {
            if (!File.Exists(MetaPath)) return null;
            await using var stream = File.OpenRead(MetaPath);
            using var document = await JsonDocument.ParseAsync(stream, cancellationToken: cancellationToken);
            var root = document.RootElement;
            if (!root.TryGetProperty("updatedUtc", out var value) || value.ValueKind != JsonValueKind.String) return null;
            if (!DateTimeOffset.TryParse(value.GetString(), out var updated)) return null;
            return DateTimeOffset.UtcNow - updated;
        }
        catch { return null; }
    }

    public async Task<BlocklistUpdateResult> UpdateAsync(IProgress<string>? progress = null, CancellationToken cancellationToken = default)
    {
        Directory.CreateDirectory(DirectoryPath);
        var errors = new List<string>();
        var sources = new List<string>();
        var domainTexts = new List<string>();

        foreach (var urls in DomainSources)
        {
            try
            {
                var (data, used) = await DownloadAnyAsync(urls, cancellationToken);
                domainTexts.Add(Encoding.UTF8.GetString(data));
                sources.Add(used);
                progress?.Report($"Доменные списки: загружено {data.Length / 1024} КБ");
            }
            catch (Exception ex)
            {
                errors.Add("domains: " + ex.Message);
                progress?.Report("Доменные списки: ошибка, пробую локальный кэш");
            }
        }

        var domainPath = Path.Combine(DirectoryPath, "ru_domains.json");
        var domainCount = 0;
        if (domainTexts.Count > 0)
        {
            domainCount = await BuildDomainRuleSetAsync(domainTexts, domainPath, cancellationToken);
        }
        else if (!File.Exists(domainPath))
        {
            throw new InvalidOperationException("Не удалось получить доменные списки и локального кэша ещё нет");
        }

        var serviceTexts = new List<string> { YouTubeFallback };
        foreach (var (service, urls) in ServiceSources)
        {
            try
            {
                var (data, used) = await DownloadAnyAsync(urls, cancellationToken);
                serviceTexts.Add(Encoding.UTF8.GetString(data));
                sources.Add(used);
                progress?.Report($"Сервис {service}: загружен");
            }
            catch (Exception ex)
            {
                errors.Add(service + ": " + ex.Message);
                progress?.Report($"Сервис {service}: недоступен, продолжаю");
            }
        }

        var servicePath = Path.Combine(DirectoryPath, "service_domains.json");
        var serviceCount = await BuildDomainRuleSetAsync(serviceTexts, servicePath, cancellationToken);

        foreach (var (name, urls) in IpSources)
        {
            var destination = Path.Combine(DirectoryPath, name + ".srs");
            try
            {
                var (data, used) = await DownloadAnyAsync(urls, cancellationToken);
                await AtomicWriteBytesAsync(destination, data, cancellationToken);
                sources.Add(used);
                progress?.Report($"IP rule-set {name}: обновлён ({data.Length / 1024} КБ)");
            }
            catch (Exception ex)
            {
                errors.Add(name + ": " + ex.Message);
                if (File.Exists(destination)) progress?.Report($"IP rule-set {name}: используется кэш");
            }
        }

        var result = new BlocklistUpdateResult(
            DateTimeOffset.UtcNow,
            domainCount,
            serviceCount,
            GetCachedPaths(),
            sources,
            errors);

        var meta = new JsonObject
        {
            ["updatedUtc"] = result.UpdatedUtc.ToString("O"),
            ["domainCount"] = result.DomainCount,
            ["serviceDomainCount"] = result.ServiceDomainCount,
            ["paths"] = new JsonArray(result.Paths.Select(x => (JsonNode?)x).ToArray()),
            ["sources"] = new JsonArray(result.Sources.Select(x => (JsonNode?)x).ToArray()),
            ["errors"] = new JsonArray(result.Errors.Select(x => (JsonNode?)x).ToArray()),
        };
        await AtomicWriteTextAsync(MetaPath, meta.ToJsonString(new JsonSerializerOptions { WriteIndented = true }), cancellationToken);
        return result;
    }

    private async Task<(byte[] Data, string Url)> DownloadAnyAsync(IEnumerable<string> urls, CancellationToken cancellationToken)
    {
        Exception? last = null;
        foreach (var url in urls)
        {
            try
            {
                using var response = await _httpClient.GetAsync(url, cancellationToken);
                response.EnsureSuccessStatusCode();
                var data = await response.Content.ReadAsByteArrayAsync(cancellationToken);
                if (data.Length == 0) throw new IOException("сервер вернул пустой файл");
                return (data, url);
            }
            catch (Exception ex) when (ex is not OperationCanceledException)
            {
                last = ex;
            }
        }
        throw new InvalidOperationException("не удалось скачать список", last);
    }

    private static async Task<int> BuildDomainRuleSetAsync(IEnumerable<string> texts, string destination, CancellationToken cancellationToken)
    {
        var exact = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var suffix = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var regex = new HashSet<string>(StringComparer.Ordinal);
        var keyword = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        foreach (var text in texts)
        {
            foreach (var raw in text.Split(['\r', '\n'], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
            {
                var line = raw.Trim();
                if (line.Length == 0 || line.StartsWith('#') || line.StartsWith('!') || line.StartsWith("//", StringComparison.Ordinal)) continue;
                if (line.StartsWith("domain:", StringComparison.OrdinalIgnoreCase)) AddDomain(suffix, line[7..]);
                else if (line.StartsWith("full:", StringComparison.OrdinalIgnoreCase)) AddDomain(exact, line[5..]);
                else if (line.StartsWith("regexp:", StringComparison.OrdinalIgnoreCase)) regex.Add(line[7..].Trim());
                else if (line.StartsWith("keyword:", StringComparison.OrdinalIgnoreCase)) keyword.Add(line[8..].Trim());
                else AddDomain(suffix, line.Split(' ', '\t')[0]);
            }
        }
        exact.ExceptWith(suffix);

        var rules = new JsonArray();
        AddChunks(rules, "domain_suffix", suffix.OrderBy(x => x).ToArray(), 6000);
        AddChunks(rules, "domain", exact.OrderBy(x => x).ToArray(), 6000);
        AddChunks(rules, "domain_regex", regex.OrderBy(x => x).ToArray(), 1500);
        AddChunks(rules, "domain_keyword", keyword.OrderBy(x => x).ToArray(), 1500);

        var payload = new JsonObject { ["version"] = 3, ["rules"] = rules };
        await AtomicWriteTextAsync(destination, payload.ToJsonString(), cancellationToken);
        return exact.Count + suffix.Count + regex.Count + keyword.Count;
    }

    private static void AddDomain(HashSet<string> destination, string value)
    {
        var domain = value.Trim().Trim('.').ToLowerInvariant();
        if (domain.Length == 0 || domain.Contains('/') || domain.Contains(':') || domain.Contains(' ')) return;
        destination.Add(domain);
    }

    private static void AddChunks(JsonArray rules, string field, string[] values, int size)
    {
        for (var index = 0; index < values.Length; index += size)
        {
            var chunk = values.Skip(index).Take(size).Select(x => (JsonNode?)x).ToArray();
            rules.Add(new JsonObject { [field] = new JsonArray(chunk) });
        }
    }

    private static async Task AtomicWriteTextAsync(string path, string text, CancellationToken cancellationToken)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        var temp = path + ".tmp";
        await File.WriteAllTextAsync(temp, text, new UTF8Encoding(false), cancellationToken);
        File.Move(temp, path, true);
    }

    private static async Task AtomicWriteBytesAsync(string path, byte[] data, CancellationToken cancellationToken)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        var temp = path + ".tmp";
        await File.WriteAllBytesAsync(temp, data, cancellationToken);
        File.Move(temp, path, true);
    }

    private static HttpClient CreateClient()
    {
        var client = new HttpClient { Timeout = TimeSpan.FromSeconds(30) };
        client.DefaultRequestHeaders.UserAgent.ParseAdd("ProstoKVN-Network/2.0");
        client.DefaultRequestHeaders.CacheControl = new System.Net.Http.Headers.CacheControlHeaderValue { NoCache = true };
        return client;
    }
}

public sealed record BlocklistUpdateResult(
    DateTimeOffset UpdatedUtc,
    int DomainCount,
    int ServiceDomainCount,
    IReadOnlyList<string> Paths,
    IReadOnlyList<string> Sources,
    IReadOnlyList<string> Errors);
