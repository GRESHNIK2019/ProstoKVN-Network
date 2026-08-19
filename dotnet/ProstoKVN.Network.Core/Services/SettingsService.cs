using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;
using ProstoKVN.Network.Core.Models;

namespace ProstoKVN.Network.Core.Services;

public sealed class SettingsService
{
    private readonly JsonSerializerOptions _jsonOptions = new()
    {
        WriteIndented = true,
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        PropertyNameCaseInsensitive = true,
        Converters = { new JsonStringEnumConverter(JsonNamingPolicy.CamelCase) },
    };

    public SettingsService(string? baseDirectory = null)
    {
        BaseDirectory = baseDirectory ?? Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "ProstoKVN Network");
        SettingsPath = Path.Combine(BaseDirectory, "settings.v2.json");
        LegacySettingsPath = Path.Combine(BaseDirectory, "settings.json");
    }

    public string BaseDirectory { get; }
    public string SettingsPath { get; }
    public string LegacySettingsPath { get; }
    public string RuntimeDirectory => Path.Combine(BaseDirectory, "runtime");
    public string CoresDirectory => Path.Combine(BaseDirectory, "cores");

    public async Task<AppSettings> LoadAsync(CancellationToken cancellationToken = default)
    {
        Directory.CreateDirectory(BaseDirectory);

        var modern = await ReadModernAsync(SettingsPath, cancellationToken)
            ?? await ReadModernAsync(SettingsPath + ".bak", cancellationToken);
        if (modern is not null)
        {
            EnsureDefaults(modern);
            return modern;
        }

        var legacy = await ReadLegacyAsync(LegacySettingsPath, cancellationToken)
            ?? await ReadLegacyAsync(LegacySettingsPath + ".bak", cancellationToken);
        if (legacy is not null)
        {
            EnsureDefaults(legacy);
            // Сохраняем импорт отдельно: Python settings.json не трогаем, поэтому
            // до завершения миграции можно безопасно вернуться к старой версии.
            await SaveAsync(legacy, cancellationToken);
            return legacy;
        }

        var defaults = new AppSettings();
        EnsureDefaults(defaults);
        return defaults;
    }

    public async Task SaveAsync(AppSettings settings, CancellationToken cancellationToken = default)
    {
        EnsureDefaults(settings);
        settings.SchemaVersion = 2;
        Directory.CreateDirectory(BaseDirectory);

        var temp = SettingsPath + ".tmp";
        var backup = SettingsPath + ".bak";
        var json = JsonSerializer.Serialize(settings, _jsonOptions) + Environment.NewLine;

        await File.WriteAllTextAsync(temp, json, new UTF8Encoding(false), cancellationToken);
        File.Move(temp, SettingsPath, true);
        File.Copy(SettingsPath, backup, true);
    }

    public string ProtectSecret(string value)
    {
        if (string.IsNullOrEmpty(value)) return string.Empty;
        var plain = Encoding.UTF8.GetBytes(value);
        var protectedBytes = ProtectedData.Protect(plain, null, DataProtectionScope.CurrentUser);
        return "dpapi:" + Convert.ToBase64String(protectedBytes);
    }

    public string UnprotectSecret(string value)
    {
        if (string.IsNullOrWhiteSpace(value)) return string.Empty;
        value = value.Trim();

        if (value.StartsWith("plain:", StringComparison.OrdinalIgnoreCase))
        {
            try { return Encoding.UTF8.GetString(Convert.FromBase64String(value[6..])); }
            catch { return string.Empty; }
        }

        if (value.StartsWith("dpapi:", StringComparison.OrdinalIgnoreCase))
        {
            try
            {
                var protectedBytes = Convert.FromBase64String(value[6..]);
                var plain = ProtectedData.Unprotect(protectedBytes, null, DataProtectionScope.CurrentUser);
                return Encoding.UTF8.GetString(plain);
            }
            catch
            {
                return string.Empty;
            }
        }

        // Совместимость с очень ранними C# preview, где DPAPI Base64 не имел префикса.
        try
        {
            var protectedBytes = Convert.FromBase64String(value);
            var plain = ProtectedData.Unprotect(protectedBytes, null, DataProtectionScope.CurrentUser);
            return Encoding.UTF8.GetString(plain);
        }
        catch
        {
            // Старые Python-версии до DPAPI хранили URL открытым текстом.
            return value;
        }
    }

    private async Task<AppSettings?> ReadModernAsync(string path, CancellationToken cancellationToken)
    {
        if (!File.Exists(path)) return null;
        try
        {
            var json = await File.ReadAllTextAsync(path, cancellationToken);
            return JsonSerializer.Deserialize<AppSettings>(json, _jsonOptions);
        }
        catch
        {
            return null;
        }
    }

    private async Task<AppSettings?> ReadLegacyAsync(string path, CancellationToken cancellationToken)
    {
        if (!File.Exists(path)) return null;
        try
        {
            var json = await File.ReadAllTextAsync(path, cancellationToken);
            var root = JsonNode.Parse(json)?.AsObject();
            if (root is null) return null;

            var settings = new AppSettings
            {
                SchemaVersion = 2,
                ActiveSubscriptionId = GetString(root, "active_subscription_id") ?? string.Empty,
                SingBoxPath = GetString(root, "singbox_path") ?? string.Empty,
                XrayPath = GetString(root, "xray_path") ?? string.Empty,
                Theme = LegacyTheme(GetString(root, "theme_mode")),
                RouteMode = LegacyRouteMode(GetString(root, "route_strategy")),
                AutoReconnect = GetBool(root, "auto_reconnect", true),
            };

            if (root["subscriptions"] is JsonArray subscriptions)
            {
                foreach (var raw in subscriptions.OfType<JsonObject>())
                {
                    var sub = new Subscription
                    {
                        Id = GetString(raw, "id") ?? Guid.NewGuid().ToString("N")[..12],
                        Name = GetString(raw, "name")?.Trim() is { Length: > 0 } name ? name : "Подписка",
                        ProtectedUrl = GetString(raw, "url") ?? string.Empty,
                        Enabled = GetBool(raw, "enabled", true),
                        UpdateIntervalMinutes = GetIntFlexible(raw, "update_interval", 0),
                        SortOrder = GetIntFlexible(raw, "sort_order", 1),
                    };
                    var lastUpdate = GetDoubleFlexible(raw, "last_update", 0);
                    if (lastUpdate > 0)
                    {
                        try { sub.LastUpdateUtc = DateTimeOffset.FromUnixTimeSeconds((long)lastUpdate); }
                        catch { }
                    }
                    settings.Subscriptions.Add(sub);
                }
            }

            if (settings.Subscriptions.Count == 0)
            {
                settings.Subscriptions.Add(new Subscription
                {
                    Name = GetString(root, "subscription_name") ?? "import_sub",
                    ProtectedUrl = GetString(root, "subscription_url") ?? string.Empty,
                    Enabled = GetBool(root, "subscription_enabled", true),
                    UpdateIntervalMinutes = GetIntFlexible(root, "subscription_interval", 0),
                    SortOrder = GetIntFlexible(root, "subscription_sort", 1),
                });
            }

            if (root["route_rules"] is JsonArray routeRules)
            {
                foreach (var raw in routeRules.OfType<JsonObject>())
                {
                    var value = GetString(raw, "value") ?? string.Empty;
                    if (value.Length == 0) continue;
                    settings.RouteRules.Add(new RouteRule
                    {
                        Type = (GetString(raw, "type") ?? string.Empty).ToLowerInvariant() switch
                        {
                            "domain_suffix" => RouteRuleType.DomainSuffix,
                            "ip_cidr" => RouteRuleType.IpCidr,
                            _ => RouteRuleType.Process,
                        },
                        Value = value,
                        Action = (GetString(raw, "action") ?? string.Empty).ToLowerInvariant() switch
                        {
                            "direct" => RouteAction.Direct,
                            "block" => RouteAction.Block,
                            _ => RouteAction.Proxy,
                        },
                    });
                }
            }

            // В версиях до новой страницы маршрутизации список приложений жил отдельно.
            if (root["custom_vpn_processes"] is JsonArray legacyProcesses)
            {
                foreach (var process in legacyProcesses)
                {
                    var value = process?.GetValue<string>()?.Trim() ?? string.Empty;
                    if (value.Length == 0) continue;
                    if (settings.RouteRules.Any(x => x.Type == RouteRuleType.Process && x.Value.Equals(value, StringComparison.OrdinalIgnoreCase))) continue;
                    settings.RouteRules.Add(new RouteRule { Type = RouteRuleType.Process, Value = value, Action = RouteAction.Proxy });
                }
            }

            settings.RouteRules = RoutingConfigService.NormalizeRouteRules(settings.RouteRules).ToList();
            return settings;
        }
        catch
        {
            return null;
        }
    }

    private static RouteMode LegacyRouteMode(string? value) => value?.Trim().ToLowerInvariant() switch
    {
        "game_only" => RouteMode.Applications,
        "global" => RouteMode.Global,
        _ => RouteMode.Smart,
    };

    private static string LegacyTheme(string? value) => value?.Trim().ToLowerInvariant() switch
    {
        "dark" => "Dark",
        "light" => "Light",
        _ => "System",
    };

    private static string? GetString(JsonObject obj, string key)
    {
        try
        {
            var node = obj[key];
            return node is null ? null : node.GetValue<string>();
        }
        catch { return obj[key]?.ToString(); }
    }

    private static bool GetBool(JsonObject obj, string key, bool fallback)
    {
        try { return obj[key]?.GetValue<bool>() ?? fallback; }
        catch
        {
            var text = obj[key]?.ToString()?.Trim().ToLowerInvariant();
            return text switch { "1" or "true" or "yes" or "on" => true, "0" or "false" or "no" or "off" => false, _ => fallback };
        }
    }

    private static int GetIntFlexible(JsonObject obj, string key, int fallback)
    {
        try { return obj[key]?.GetValue<int>() ?? fallback; }
        catch { return int.TryParse(obj[key]?.ToString(), out var value) ? value : fallback; }
    }

    private static double GetDoubleFlexible(JsonObject obj, string key, double fallback)
    {
        try { return obj[key]?.GetValue<double>() ?? fallback; }
        catch { return double.TryParse(obj[key]?.ToString(), System.Globalization.CultureInfo.InvariantCulture, out var value) ? value : fallback; }
    }

    private static void EnsureDefaults(AppSettings settings)
    {
        settings.Subscriptions ??= [];
        settings.RouteRules ??= [];
        if (settings.Subscriptions.Count == 0)
        {
            settings.Subscriptions.Add(new Subscription { Name = "import_sub" });
        }

        if (string.IsNullOrWhiteSpace(settings.ActiveSubscriptionId)
            || settings.Subscriptions.All(x => x.Id != settings.ActiveSubscriptionId))
        {
            settings.ActiveSubscriptionId = settings.Subscriptions[0].Id;
        }

        settings.RouteRules = RoutingConfigService.NormalizeRouteRules(settings.RouteRules).ToList();
    }
}
