using System.Text.Json.Nodes;
using ProstoKVN.Network.Core.Models;

namespace ProstoKVN.Network.Core.Services;

public sealed class XrayConfigService
{
    public JsonObject BuildSocksBridge(NodeModel node, int port, string logPath)
    {
        if (!node.Protocol.Equals("vless", StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("Xray bridge используется только для VLESS");

        return new JsonObject
        {
            ["log"] = new JsonObject { ["loglevel"] = "warning", ["error"] = logPath },
            ["inbounds"] = new JsonArray(new JsonObject
            {
                ["listen"] = "127.0.0.1",
                ["port"] = port,
                ["protocol"] = "socks",
                ["settings"] = new JsonObject { ["udp"] = true, ["ip"] = "127.0.0.1" },
                ["tag"] = "test-in",
            }),
            ["outbounds"] = new JsonArray(BuildVlessOutbound(node), new JsonObject { ["protocol"] = "freedom", ["tag"] = "direct" }),
        };
    }

    public JsonObject BuildVlessOutbound(NodeModel node)
    {
        var query = node.Query;
        var encryption = Get(query, "encryption") ?? "none";
        var settings = new JsonObject
        {
            ["address"] = node.Server,
            ["port"] = node.Port,
            ["id"] = node.Outbound["uuid"]?.GetValue<string>() ?? string.Empty,
            ["encryption"] = encryption,
        };
        var flow = node.Outbound["flow"]?.GetValue<string>() ?? Get(query, "flow");
        if (!string.IsNullOrWhiteSpace(flow)) settings["flow"] = flow;

        var transport = (node.Transport.Length > 0 ? node.Transport : Get(query, "type", "network") ?? "raw").ToLowerInvariant();
        var network = transport switch
        {
            "tcp" or "raw" => "raw",
            "ws" or "websocket" => "websocket",
            "grpc" => "grpc",
            "xhttp" => "xhttp",
            "httpupgrade" or "http-upgrade" => "httpupgrade",
            _ => transport,
        };
        var security = (node.Security.Length > 0 ? node.Security : Get(query, "security") ?? "none").ToLowerInvariant();
        var stream = new JsonObject { ["network"] = network, ["security"] = security };

        var path = Uri.UnescapeDataString(Get(query, "path") ?? string.Empty);
        var host = Uri.UnescapeDataString(Get(query, "host") ?? string.Empty);
        switch (network)
        {
            case "websocket":
            {
                var ws = new JsonObject();
                if (path.Length > 0) ws["path"] = path;
                if (host.Length > 0) ws["host"] = host;
                stream["wsSettings"] = ws;
                break;
            }
            case "grpc":
            {
                var service = Uri.UnescapeDataString(Get(query, "serviceName", "service_name", "service-name") ?? path);
                var grpc = new JsonObject();
                if (service.Length > 0) grpc["serviceName"] = service;
                var authority = Get(query, "authority");
                if (!string.IsNullOrWhiteSpace(authority)) grpc["authority"] = Uri.UnescapeDataString(authority);
                stream["grpcSettings"] = grpc;
                break;
            }
            case "xhttp":
            {
                var xhttp = new JsonObject();
                if (path.Length > 0) xhttp["path"] = path;
                if (host.Length > 0) xhttp["host"] = host;
                var mode = Get(query, "mode");
                if (!string.IsNullOrWhiteSpace(mode)) xhttp["mode"] = mode;
                stream["xhttpSettings"] = xhttp;
                break;
            }
            case "httpupgrade":
            {
                var upgrade = new JsonObject();
                if (path.Length > 0) upgrade["path"] = path;
                if (host.Length > 0) upgrade["host"] = host;
                stream["httpupgradeSettings"] = upgrade;
                break;
            }
        }

        var sni = Uri.UnescapeDataString(Get(query, "sni", "serverName", "servername") ?? string.Empty);
        var fingerprint = Get(query, "fp", "fingerprint", "client-fingerprint") ?? "chrome";
        if (security == "tls")
        {
            var tls = new JsonObject { ["allowInsecure"] = AsBool(Get(query, "allowInsecure", "insecure", "skip-cert-verify")) };
            if (sni.Length > 0) tls["serverName"] = sni;
            if (fingerprint.Length > 0) tls["fingerprint"] = fingerprint;
            stream["tlsSettings"] = tls;
        }
        else if (security == "reality")
        {
            var reality = new JsonObject { ["fingerprint"] = fingerprint };
            if (sni.Length > 0) reality["serverName"] = sni;
            var publicKey = Get(query, "pbk", "publicKey", "public_key");
            if (!string.IsNullOrWhiteSpace(publicKey)) reality["publicKey"] = publicKey;
            var shortId = Get(query, "sid", "shortId", "short_id");
            if (!string.IsNullOrWhiteSpace(shortId)) reality["shortId"] = shortId;
            var spiderX = Uri.UnescapeDataString(Get(query, "spx", "spiderX") ?? string.Empty);
            if (spiderX.Length > 0) reality["spiderX"] = spiderX;
            stream["realitySettings"] = reality;
        }

        return new JsonObject
        {
            ["protocol"] = "vless",
            ["tag"] = "proxy",
            ["settings"] = settings,
            ["streamSettings"] = stream,
        };
    }

    private static string? Get(IReadOnlyDictionary<string, string> values, params string[] names)
    {
        foreach (var name in names)
            if (values.TryGetValue(name, out var value)) return value;
        return null;
    }

    private static bool AsBool(string? value) => value?.Trim().ToLowerInvariant() is "1" or "true" or "yes" or "on" or "enable" or "enabled";
}
