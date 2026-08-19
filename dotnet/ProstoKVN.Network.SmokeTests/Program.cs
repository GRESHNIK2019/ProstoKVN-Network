using System.Text;
using System.Text.Json.Nodes;
using ProstoKVN.Network.Core.Models;
using ProstoKVN.Network.Core.Services;

static void Assert(bool condition, string message)
{
    if (!condition) throw new InvalidOperationException("SMOKE TEST FAILED: " + message);
}

var vless = NodeParser.ParseShareLink(
    "vless://11111111-1111-1111-1111-111111111111@example.com:443?type=xhttp&security=reality&sni=example.com&pbk=test-public-key&sid=01#XHTTP");
Assert(vless.Protocol == "vless", "VLESS protocol");
Assert(vless.Transport == "xhttp", "VLESS XHTTP transport");
Assert(vless.Security == "reality", "VLESS REALITY security");
Assert(vless.Engine == "xray", "VLESS must use Xray");
Assert(vless.StackLabel == "VLESS + XHTTP + REALITY", "VLESS stack label");

var xray = new XrayConfigService().BuildVlessOutbound(vless);
var stream = xray["streamSettings"]?.AsObject() ?? throw new InvalidOperationException("streamSettings missing");
Assert(stream["network"]?.GetValue<string>() == "xhttp", "Xray must use streamSettings.network");
var reality = stream["realitySettings"]?.AsObject() ?? throw new InvalidOperationException("realitySettings missing");
Assert(reality["publicKey"]?.GetValue<string>() == "test-public-key", "REALITY publicKey");

var trojan = NodeParser.ParseShareLink("trojan://secret@example.org:443?security=tls&type=ws&path=%2Fws#Trojan");
Assert(trojan.Protocol == "trojan", "Trojan protocol");
Assert(trojan.Transport == "ws", "Trojan WS transport");

var ssCredentials = Convert.ToBase64String(Encoding.UTF8.GetBytes("aes-256-gcm:password")).TrimEnd('=');
var shadowsocks = NodeParser.ParseShareLink($"ss://{ssCredentials}@127.0.0.1:8388#SS");
Assert(shadowsocks.Protocol == "shadowsocks", "Shadowsocks protocol");
Assert(shadowsocks.Port == 8388, "Shadowsocks port");

var vmessPayload = "{\"v\":\"2\",\"ps\":\"VMess\",\"add\":\"vmess.example\",\"port\":\"443\",\"id\":\"11111111-1111-1111-1111-111111111111\",\"aid\":\"0\",\"net\":\"ws\",\"host\":\"vmess.example\",\"path\":\"/socket\",\"tls\":\"tls\"}";
var vmessBase64 = Convert.ToBase64String(Encoding.UTF8.GetBytes(vmessPayload)).TrimEnd('=');
var vmess = NodeParser.ParseShareLink("vmess://" + vmessBase64);
Assert(vmess.Protocol == "vmess", "VMess protocol");
Assert(vmess.Transport == "ws", "VMess WS transport");

var normalized = RoutingConfigService.NormalizeRouteRules([
    new RouteRule { Type = RouteRuleType.Process, Value = @"C:\Games\Steam", Action = RouteAction.Direct },
    new RouteRule { Type = RouteRuleType.DomainSuffix, Value = "*.ubisoft.com", Action = RouteAction.Proxy },
    new RouteRule { Type = RouteRuleType.IpCidr, Value = "8.8.8.8", Action = RouteAction.Block },
]).ToArray();
Assert(normalized[0].Value.Equals("Steam.exe", StringComparison.OrdinalIgnoreCase), "process normalization");
Assert(normalized[1].Value == ".ubisoft.com", "domain suffix normalization");
Assert(normalized[2].Value == "8.8.8.8/32", "CIDR normalization");

var settings = new AppSettings
{
    RouteMode = RouteMode.Smart,
    RouteRules = normalized.ToList(),
};
var routing = new RoutingConfigService();
var (rules, _, finalOutbound) = routing.BuildRouteRules(settings, []);
Assert(finalOutbound == "direct", "Smart final route");
Assert(rules.Count >= 7, "expected builtin and custom rules");

var customProcessRule = rules[3]?.AsObject() ?? throw new InvalidOperationException("custom process rule missing");
Assert(customProcessRule["process_name"]?[0]?.GetValue<string>() == "Steam.exe", "custom rules must precede builtin Steam rule");
Assert(customProcessRule["outbound"]?.GetValue<string>() == "direct", "custom DIRECT action");

settings.RouteMode = RouteMode.Global;
var (_, _, globalFinal) = routing.BuildRouteRules(settings, []);
Assert(globalFinal == "proxy", "Global final route");

var encodedSubscription = Convert.ToBase64String(Encoding.UTF8.GetBytes(
    "trojan://secret@example.org:443?security=tls&type=ws#One\n" +
    "vless://11111111-1111-1111-1111-111111111111@example.net:443?type=grpc&security=reality&pbk=key#Two"));
var parsedPayload = NodeParser.ParsePayload(encodedSubscription);
Assert(parsedPayload.Count == 2, "base64 subscription payload");

Console.WriteLine("C# Core smoke tests: OK");
