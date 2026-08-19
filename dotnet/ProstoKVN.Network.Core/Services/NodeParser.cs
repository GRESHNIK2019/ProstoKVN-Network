using System.Net;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using ProstoKVN.Network.Core.Models;

namespace ProstoKVN.Network.Core.Services;

public static class NodeParser
{
    private static readonly HashSet<string> Supported = new(StringComparer.OrdinalIgnoreCase)
    {
        "vless", "vmess", "trojan", "ss", "hysteria2", "hy2", "tuic",
    };

    public static NodeModel ParseShareLink(string link)
    {
        if (string.IsNullOrWhiteSpace(link)) throw new ArgumentException("Пустая ссылка узла", nameof(link));
        var schemeEnd = link.IndexOf("://", StringComparison.Ordinal);
        if (schemeEnd <= 0) throw new FormatException("Ссылка не содержит протокол");
        var scheme = link[..schemeEnd].ToLowerInvariant();
        if (!Supported.Contains(scheme)) throw new NotSupportedException($"Протокол {scheme} не поддерживается");

        return scheme switch
        {
            "vless" => ParseVless(link),
            "vmess" => ParseVmess(link),
            "trojan" => ParseTrojan(link),
            "ss" => ParseShadowsocks(link),
            "hysteria2" or "hy2" => ParseHysteria2(link),
            "tuic" => ParseTuic(link),
            _ => throw new NotSupportedException(scheme),
        };
    }

    public static IReadOnlyList<NodeModel> ParsePayload(string payload)
    {
        if (string.IsNullOrWhiteSpace(payload)) return [];

        var text = payload.Trim();
        if (!text.Contains("://", StringComparison.Ordinal))
        {
            try
            {
                var decoded = Encoding.UTF8.GetString(DecodeBase64Loose(text));
                if (decoded.Contains("://", StringComparison.Ordinal)) text = decoded;
            }
            catch
            {
                // Это может быть обычный многострочный список, а не Base64.
            }
        }

        var result = new List<NodeModel>();
        var seen = new HashSet<string>(StringComparer.Ordinal);
        foreach (var raw in text.Split(['\r', '\n'], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
        {
            var line = raw.Trim();
            if (!line.Contains("://", StringComparison.Ordinal)) continue;
            try
            {
                var node = ParseShareLink(line);
                var key = $"{node.Protocol}|{node.Server}|{node.Port}|{node.Name}";
                if (seen.Add(key)) result.Add(node);
            }
            catch
            {
                // Некорректный узел не должен ломать всю подписку.
            }
        }
        return result;
    }

    private static NodeModel ParseVless(string link)
    {
        var uri = new Uri(link);
        var query = ParseQuery(uri.Query);
        var transport = Get(query, "type", "network", "net")?.ToLowerInvariant() ?? "raw";
        var security = Get(query, "security")?.ToLowerInvariant() ?? "none";
        var uuid = Uri.UnescapeDataString(uri.UserInfo.Split(':')[0]);
        var outbound = new JsonObject
        {
            ["type"] = "vless",
            ["tag"] = "proxy",
            ["server"] = uri.Host,
            ["server_port"] = uri.Port > 0 ? uri.Port : 443,
            ["uuid"] = uuid,
        };

        var flow = Get(query, "flow");
        if (!string.IsNullOrWhiteSpace(flow)) outbound["flow"] = flow;
        var packetEncoding = Get(query, "packetEncoding", "packet_encoding");
        if (!string.IsNullOrWhiteSpace(packetEncoding)) outbound["packet_encoding"] = packetEncoding;

        var tls = BuildSingBoxTls(query, security, uri.Host);
        if (tls is not null) outbound["tls"] = tls;
        if (!transport.Equals("xhttp", StringComparison.OrdinalIgnoreCase))
        {
            var tr = BuildSingBoxTransport(query, transport);
            if (tr is not null) outbound["transport"] = tr;
        }

        return CreateNode(link, uri, "vless", outbound, transport, security, "xray", query);
    }

    private static NodeModel ParseTrojan(string link)
    {
        var uri = new Uri(link);
        var query = ParseQuery(uri.Query);
        var transport = Get(query, "type", "network", "net")?.ToLowerInvariant() ?? "raw";
        var security = Get(query, "security")?.ToLowerInvariant() ?? "tls";
        var password = Uri.UnescapeDataString(uri.UserInfo.Split(':')[0]);
        var outbound = new JsonObject
        {
            ["type"] = "trojan",
            ["tag"] = "proxy",
            ["server"] = uri.Host,
            ["server_port"] = uri.Port > 0 ? uri.Port : 443,
            ["password"] = password,
        };
        var tls = BuildSingBoxTls(query, security, uri.Host);
        if (tls is not null) outbound["tls"] = tls;
        var tr = BuildSingBoxTransport(query, transport);
        if (tr is not null) outbound["transport"] = tr;
        return CreateNode(link, uri, "trojan", outbound, transport, security, "sing-box", query);
    }

    private static NodeModel ParseHysteria2(string link)
    {
        var uri = new Uri(link.Replace("hy2://", "hysteria2://", StringComparison.OrdinalIgnoreCase));
        var query = ParseQuery(uri.Query);
        var password = Uri.UnescapeDataString(uri.UserInfo);
        var outbound = new JsonObject
        {
            ["type"] = "hysteria2",
            ["tag"] = "proxy",
            ["server"] = uri.Host,
            ["server_port"] = uri.Port > 0 ? uri.Port : 443,
            ["password"] = password,
        };

        var tls = new JsonObject { ["enabled"] = true };
        var sni = Get(query, "sni", "peer");
        if (!string.IsNullOrWhiteSpace(sni)) tls["server_name"] = sni;
        else if (!IPAddress.TryParse(uri.Host, out _)) tls["server_name"] = uri.Host;
        if (AsBool(Get(query, "insecure", "allowInsecure"))) tls["insecure"] = true;
        outbound["tls"] = tls;

        var obfs = Get(query, "obfs");
        if (!string.IsNullOrWhiteSpace(obfs))
        {
            var obfsObj = new JsonObject { ["type"] = obfs };
            var obfsPassword = Get(query, "obfs-password", "obfs_password");
            if (!string.IsNullOrWhiteSpace(obfsPassword)) obfsObj["password"] = obfsPassword;
            outbound["obfs"] = obfsObj;
        }

        if (int.TryParse(Get(query, "upmbps", "up_mbps"), out var up) && up > 0) outbound["up_mbps"] = up;
        if (int.TryParse(Get(query, "downmbps", "down_mbps"), out var down) && down > 0) outbound["down_mbps"] = down;

        return CreateNode(link, uri, "hysteria2", outbound, "quic", "tls", "sing-box", query);
    }

    private static NodeModel ParseTuic(string link)
    {
        var uri = new Uri(link);
        var query = ParseQuery(uri.Query);
        var userInfo = uri.UserInfo.Split(':', 2);
        var outbound = new JsonObject
        {
            ["type"] = "tuic",
            ["tag"] = "proxy",
            ["server"] = uri.Host,
            ["server_port"] = uri.Port > 0 ? uri.Port : 443,
            ["uuid"] = Uri.UnescapeDataString(userInfo[0]),
            ["password"] = userInfo.Length > 1 ? Uri.UnescapeDataString(userInfo[1]) : string.Empty,
        };
        var cc = Get(query, "congestion_control", "congestion-control");
        if (!string.IsNullOrWhiteSpace(cc)) outbound["congestion_control"] = cc;
        var relay = Get(query, "udp_relay_mode", "udp-relay-mode");
        if (!string.IsNullOrWhiteSpace(relay)) outbound["udp_relay_mode"] = relay;

        var tls = new JsonObject { ["enabled"] = true };
        var sni = Get(query, "sni", "peer");
        if (!string.IsNullOrWhiteSpace(sni)) tls["server_name"] = sni;
        else if (!IPAddress.TryParse(uri.Host, out _)) tls["server_name"] = uri.Host;
        if (AsBool(Get(query, "insecure", "allowInsecure"))) tls["insecure"] = true;
        outbound["tls"] = tls;

        return CreateNode(link, uri, "tuic", outbound, "quic", "tls", "sing-box", query);
    }

    private static NodeModel ParseVmess(string link)
    {
        var raw = link["vmess://".Length..];
        var fragmentIndex = raw.IndexOf('#');
        if (fragmentIndex >= 0) raw = raw[..fragmentIndex];
        var json = Encoding.UTF8.GetString(DecodeBase64Loose(raw));
        using var document = JsonDocument.Parse(json);
        var root = document.RootElement;

        var server = ReadString(root, "add");
        var port = int.TryParse(ReadString(root, "port"), out var parsedPort) ? parsedPort : 443;
        var name = ReadString(root, "ps");
        if (string.IsNullOrWhiteSpace(name)) name = $"VMess {server}:{port}";
        var transport = ReadString(root, "net").ToLowerInvariant();
        if (string.IsNullOrWhiteSpace(transport)) transport = "raw";
        var security = ReadString(root, "tls").ToLowerInvariant();
        if (string.IsNullOrWhiteSpace(security)) security = "none";

        var outbound = new JsonObject
        {
            ["type"] = "vmess",
            ["tag"] = "proxy",
            ["server"] = server,
            ["server_port"] = port,
            ["uuid"] = ReadString(root, "id"),
            ["security"] = "auto",
        };
        if (int.TryParse(ReadString(root, "aid"), out var alterId) && alterId > 0) outbound["alter_id"] = alterId;

        var query = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
        {
            ["type"] = transport,
            ["security"] = security,
            ["host"] = ReadString(root, "host"),
            ["path"] = ReadString(root, "path"),
            ["sni"] = ReadString(root, "sni"),
        };
        var tls = BuildSingBoxTls(query, security, server);
        if (tls is not null) outbound["tls"] = tls;
        var tr = BuildSingBoxTransport(query, transport);
        if (tr is not null) outbound["transport"] = tr;

        return new NodeModel
        {
            Name = name,
            Protocol = "vmess",
            Server = server,
            Port = port,
            Outbound = outbound,
            Source = link,
            Transport = transport,
            Security = security,
            Engine = "sing-box",
            Query = query,
        };
    }

    private static NodeModel ParseShadowsocks(string link)
    {
        var raw = link["ss://".Length..];
        var fragment = string.Empty;
        var hash = raw.IndexOf('#');
        if (hash >= 0)
        {
            fragment = Uri.UnescapeDataString(raw[(hash + 1)..]);
            raw = raw[..hash];
        }
        var question = raw.IndexOf('?');
        if (question >= 0) raw = raw[..question];

        string credentials;
        string address;
        if (raw.Contains('@'))
        {
            var at = raw.LastIndexOf('@');
            var userPart = raw[..at];
            address = raw[(at + 1)..];
            try { credentials = Encoding.UTF8.GetString(DecodeBase64Loose(userPart)); }
            catch { credentials = Uri.UnescapeDataString(userPart); }
        }
        else
        {
            var decoded = Encoding.UTF8.GetString(DecodeBase64Loose(raw));
            var at = decoded.LastIndexOf('@');
            if (at < 0) throw new FormatException("Shadowsocks: отсутствует адрес");
            credentials = decoded[..at];
            address = decoded[(at + 1)..];
        }

        var colon = credentials.IndexOf(':');
        if (colon < 0) throw new FormatException("Shadowsocks: отсутствует method:password");
        var method = Uri.UnescapeDataString(credentials[..colon]);
        var password = Uri.UnescapeDataString(credentials[(colon + 1)..]);
        var addressUri = new Uri("ss://x@" + address);
        var name = string.IsNullOrWhiteSpace(fragment) ? $"SS {addressUri.Host}:{addressUri.Port}" : fragment;
        var outbound = new JsonObject
        {
            ["type"] = "shadowsocks",
            ["tag"] = "proxy",
            ["server"] = addressUri.Host,
            ["server_port"] = addressUri.Port,
            ["method"] = method,
            ["password"] = password,
        };

        return new NodeModel
        {
            Name = name,
            Protocol = "shadowsocks",
            Server = addressUri.Host,
            Port = addressUri.Port,
            Outbound = outbound,
            Source = link,
            Engine = "sing-box",
        };
    }

    private static NodeModel CreateNode(
        string source,
        Uri uri,
        string protocol,
        JsonObject outbound,
        string transport,
        string security,
        string engine,
        IReadOnlyDictionary<string, string> query)
    {
        var name = Uri.UnescapeDataString(uri.Fragment.TrimStart('#'));
        if (string.IsNullOrWhiteSpace(name)) name = $"{protocol.ToUpperInvariant()} {uri.Host}:{uri.Port}";
        return new NodeModel
        {
            Name = name,
            Protocol = protocol,
            Server = uri.Host,
            Port = uri.Port > 0 ? uri.Port : 443,
            Outbound = outbound,
            Source = source,
            Transport = transport,
            Security = security,
            Engine = engine,
            Query = query,
        };
    }

    private static JsonObject? BuildSingBoxTls(IReadOnlyDictionary<string, string> query, string security, string server)
    {
        var reality = security.Equals("reality", StringComparison.OrdinalIgnoreCase);
        var enabled = reality || security.Equals("tls", StringComparison.OrdinalIgnoreCase) || AsBool(Get(query, "tls"));
        if (!enabled) return null;

        var tls = new JsonObject { ["enabled"] = true };
        var sni = Get(query, "sni", "serverName", "servername", "peer");
        if (!string.IsNullOrWhiteSpace(sni)) tls["server_name"] = Uri.UnescapeDataString(sni);
        else if (!IPAddress.TryParse(server, out _)) tls["server_name"] = server;
        if (AsBool(Get(query, "allowInsecure", "insecure", "skip-cert-verify"))) tls["insecure"] = true;

        var fp = Get(query, "fp", "fingerprint", "client-fingerprint");
        if (!string.IsNullOrWhiteSpace(fp) && !fp.Equals("none", StringComparison.OrdinalIgnoreCase))
        {
            tls["utls"] = new JsonObject { ["enabled"] = true, ["fingerprint"] = fp };
        }

        if (reality)
        {
            var publicKey = Get(query, "pbk", "publicKey", "public_key");
            var shortId = Get(query, "sid", "shortId", "short_id") ?? string.Empty;
            if (!string.IsNullOrWhiteSpace(publicKey))
            {
                tls["reality"] = new JsonObject
                {
                    ["enabled"] = true,
                    ["public_key"] = publicKey,
                    ["short_id"] = shortId,
                };
            }
        }
        return tls;
    }

    private static JsonObject? BuildSingBoxTransport(IReadOnlyDictionary<string, string> query, string transport)
    {
        var host = Uri.UnescapeDataString(Get(query, "host", "Host", "authority") ?? string.Empty);
        var path = Uri.UnescapeDataString(Get(query, "path") ?? string.Empty);
        return transport.ToLowerInvariant() switch
        {
            "" or "tcp" or "raw" or "none" => null,
            "ws" or "websocket" => new JsonObject
            {
                ["type"] = "ws",
                ["path"] = path,
                ["headers"] = string.IsNullOrWhiteSpace(host) ? null : new JsonObject { ["Host"] = host },
            },
            "grpc" or "gun" => new JsonObject
            {
                ["type"] = "grpc",
                ["service_name"] = Uri.UnescapeDataString(Get(query, "serviceName", "service_name", "service-name") ?? string.Empty),
            },
            "httpupgrade" or "http-upgrade" => new JsonObject { ["type"] = "httpupgrade", ["host"] = host, ["path"] = path },
            "http" or "h2" => new JsonObject { ["type"] = "http", ["host"] = new JsonArray(host), ["path"] = path },
            "quic" => new JsonObject { ["type"] = "quic" },
            _ => null,
        };
    }

    private static Dictionary<string, string> ParseQuery(string query)
    {
        var result = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        foreach (var pair in query.TrimStart('?').Split('&', StringSplitOptions.RemoveEmptyEntries))
        {
            var parts = pair.Split('=', 2);
            var key = Uri.UnescapeDataString(parts[0]);
            var value = parts.Length > 1 ? Uri.UnescapeDataString(parts[1].Replace('+', ' ')) : string.Empty;
            result[key] = value;
        }
        return result;
    }

    private static string? Get(IReadOnlyDictionary<string, string> values, params string[] keys)
    {
        foreach (var key in keys)
        {
            if (values.TryGetValue(key, out var value)) return value;
        }
        return null;
    }

    private static bool AsBool(string? value) => value?.Trim().ToLowerInvariant() is "1" or "true" or "yes" or "on" or "enable" or "enabled";

    private static byte[] DecodeBase64Loose(string value)
    {
        var text = string.Concat(value.Where(c => !char.IsWhiteSpace(c))).Replace('-', '+').Replace('_', '/');
        text += new string('=', (4 - text.Length % 4) % 4);
        return Convert.FromBase64String(text);
    }

    private static string ReadString(JsonElement root, string name)
    {
        if (!root.TryGetProperty(name, out var property)) return string.Empty;
        return property.ValueKind == JsonValueKind.String ? property.GetString() ?? string.Empty : property.ToString();
    }
}
