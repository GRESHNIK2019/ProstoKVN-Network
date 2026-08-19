using System.Net;
using System.Text.Json.Nodes;
using ProstoKVN.Network.Core.Models;

namespace ProstoKVN.Network.Core.Services;

public sealed class RoutingConfigService
{
    private static readonly string[] ProtectedDirect =
    [
        "sing-box.exe", "sing-box-client.exe", "xray.exe", "v2ray.exe",
        "ProstoKVN.Network.App.exe", "ProstoKVNNetwork.exe",
    ];

    private static readonly string[] SteamDirect = ["steam.exe", "GameOverlayUI.exe"];
    private static readonly string[] DiscordProcesses = ["Discord.exe"];
    private static readonly string[] TelegramProcesses = ["Telegram.exe"];
    private static readonly string[] RuDirectSuffixes = [".ru", ".su", ".рф", ".xn--p1ai"];

    public JsonObject BuildTunConfig(
        NodeModel node,
        string logPath,
        AppSettings settings,
        JsonObject? proxyOverride = null,
        IReadOnlyList<string>? blocklistPaths = null)
    {
        var outbound = proxyOverride?.DeepClone().AsObject() ?? node.Outbound.DeepClone().AsObject();
        outbound["tag"] = "proxy";

        var (rules, ruleSets, finalOutbound) = BuildRouteRules(settings, blocklistPaths ?? []);
        var route = new JsonObject
        {
            ["auto_detect_interface"] = true,
            ["rules"] = rules,
            ["final"] = finalOutbound,
        };
        if (ruleSets.Count > 0) route["rule_set"] = ruleSets;

        return new JsonObject
        {
            ["log"] = new JsonObject
            {
                ["level"] = "warn",
                ["timestamp"] = true,
                ["output"] = logPath,
            },
            ["dns"] = new JsonObject
            {
                ["servers"] = new JsonArray(new JsonObject { ["type"] = "local", ["tag"] = "local-dns" }),
                ["final"] = "local-dns",
                ["strategy"] = "prefer_ipv4",
                ["reverse_mapping"] = true,
                ["cache_capacity"] = 4096,
            },
            ["inbounds"] = new JsonArray(new JsonObject
            {
                ["type"] = "tun",
                ["tag"] = "prostokvn-tun",
                ["interface_name"] = "prostokvn_network_tun",
                ["address"] = new JsonArray("172.29.77.1/30"),
                ["mtu"] = 1400,
                ["auto_route"] = true,
                ["strict_route"] = false,
                ["stack"] = "system",
            }),
            ["outbounds"] = new JsonArray(outbound, new JsonObject { ["type"] = "direct", ["tag"] = "direct" }),
            ["route"] = route,
            ["experimental"] = new JsonObject
            {
                ["clash_api"] = new JsonObject
                {
                    ["external_controller"] = "127.0.0.1:19181",
                    ["secret"] = string.Empty,
                },
            },
        };
    }

    public (JsonArray Rules, JsonArray RuleSets, string FinalOutbound) BuildRouteRules(
        AppSettings settings,
        IReadOnlyList<string> blocklistPaths)
    {
        var rules = new JsonArray
        {
            new JsonObject { ["network"] = ToArray("tcp", "udp"), ["port"] = new JsonArray(53), ["action"] = "hijack-dns" },
            new JsonObject { ["action"] = "sniff" },
            RouteProcesses(ProtectedDirect, "direct"),
        };

        foreach (var rule in NormalizeRouteRules(settings.RouteRules))
        {
            var json = new JsonObject();
            switch (rule.Type)
            {
                case RouteRuleType.Process:
                    json["process_name"] = ToArray(rule.Value);
                    break;
                case RouteRuleType.DomainSuffix:
                    json["domain_suffix"] = ToArray(rule.Value);
                    break;
                case RouteRuleType.IpCidr:
                    json["ip_cidr"] = ToArray(rule.Value);
                    break;
            }

            if (rule.Action == RouteAction.Block)
            {
                json["action"] = "reject";
            }
            else
            {
                json["action"] = "route";
                json["outbound"] = rule.Action == RouteAction.Direct ? "direct" : "proxy";
            }
            rules.Add(json);
        }

        rules.Add(RouteProcesses(SteamDirect, "direct"));

        if (settings.RouteMode is RouteMode.Smart or RouteMode.Applications || settings.DiscordVpn)
            rules.Add(RouteProcesses(DiscordProcesses, "proxy"));
        if (settings.RouteMode == RouteMode.Smart)
            rules.Add(RouteProcesses(TelegramProcesses, "proxy"));
        if (settings.SteamWebHelperVpn)
            rules.Add(RouteProcesses(["steamwebhelper.exe"], "proxy"));

        rules.Add(new JsonObject
        {
            ["domain_suffix"] = ToArray(RuDirectSuffixes),
            ["action"] = "route",
            ["outbound"] = "direct",
        });

        var ruleSets = new JsonArray();
        if (settings.RouteMode == RouteMode.Smart && settings.BlockedRuVpn)
        {
            var tags = new List<string>();
            var index = 0;
            foreach (var path in blocklistPaths.Where(File.Exists))
            {
                var tag = $"ru_block_{index++}";
                tags.Add(tag);
                ruleSets.Add(new JsonObject
                {
                    ["type"] = "local",
                    ["tag"] = tag,
                    ["format"] = Path.GetExtension(path).Equals(".srs", StringComparison.OrdinalIgnoreCase) ? "binary" : "source",
                    ["path"] = path,
                });
            }
            if (tags.Count > 0)
            {
                rules.Add(new JsonObject
                {
                    ["rule_set"] = ToArray(tags),
                    ["action"] = "route",
                    ["outbound"] = "proxy",
                });
            }
        }

        return (rules, ruleSets, settings.RouteMode == RouteMode.Global ? "proxy" : "direct");
    }

    public static IReadOnlyList<RouteRule> NormalizeRouteRules(IEnumerable<RouteRule> source)
    {
        var result = new List<RouteRule>();
        var positions = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);

        foreach (var item in source ?? [])
        {
            var value = item.Value?.Trim() ?? string.Empty;
            if (value.Length == 0) continue;

            switch (item.Type)
            {
                case RouteRuleType.Process:
                    value = Path.GetFileName(value.Replace('/', '\\'));
                    if (!value.EndsWith(".exe", StringComparison.OrdinalIgnoreCase)) value += ".exe";
                    break;
                case RouteRuleType.DomainSuffix:
                    value = value.ToLowerInvariant();
                    if (value.StartsWith("*.")) value = value[1..];
                    if (value.Contains("://", StringComparison.Ordinal) || value.Contains('/') || value.Contains(' ')) continue;
                    if (!value.StartsWith('.')) value = "." + value;
                    if (value == ".") continue;
                    break;
                case RouteRuleType.IpCidr:
                    if (!TryNormalizeCidr(value, out value)) continue;
                    break;
            }

            var key = $"{item.Type}:{value}";
            var normalized = new RouteRule { Type = item.Type, Action = item.Action, Value = value };
            if (positions.TryGetValue(key, out var existing))
            {
                result[existing] = normalized;
            }
            else
            {
                positions[key] = result.Count;
                result.Add(normalized);
            }
        }

        return result;
    }

    private static bool TryNormalizeCidr(string value, out string normalized)
    {
        normalized = string.Empty;
        var parts = value.Split('/', 2);
        if (!IPAddress.TryParse(parts[0], out var address)) return false;
        if (parts.Length == 1)
        {
            normalized = address.AddressFamily == System.Net.Sockets.AddressFamily.InterNetwork
                ? address + "/32"
                : address + "/128";
            return true;
        }
        if (!int.TryParse(parts[1], out var prefix)) return false;
        var max = address.AddressFamily == System.Net.Sockets.AddressFamily.InterNetwork ? 32 : 128;
        if (prefix < 0 || prefix > max) return false;
        normalized = $"{address}/{prefix}";
        return true;
    }

    private static JsonObject RouteProcesses(IEnumerable<string> processes, string outbound) => new()
    {
        ["process_name"] = ToArray(processes),
        ["action"] = "route",
        ["outbound"] = outbound,
    };

    private static JsonArray ToArray(params string[] values) => new(values.Select(x => (JsonNode?)x).ToArray());
    private static JsonArray ToArray(IEnumerable<string> values) => new(values.Select(x => (JsonNode?)x).ToArray());
}
