using System.ComponentModel;
using System.Runtime.CompilerServices;
using System.Text.Json.Nodes;

namespace ProstoKVN.Network.Core.Models;

public enum RouteMode
{
    Smart,
    Applications,
    Global,
}

public enum RouteRuleType
{
    Process,
    DomainSuffix,
    IpCidr,
}

public enum RouteAction
{
    Proxy,
    Direct,
    Block,
}

public sealed class RouteRule
{
    public RouteRuleType Type { get; set; }
    public string Value { get; set; } = string.Empty;
    public RouteAction Action { get; set; } = RouteAction.Proxy;
}

public sealed class Subscription
{
    public string Id { get; set; } = Guid.NewGuid().ToString("N");
    public string Name { get; set; } = "import_sub";
    public string ProtectedUrl { get; set; } = string.Empty;
    public bool Enabled { get; set; } = true;
    public int UpdateIntervalMinutes { get; set; }
    public int SortOrder { get; set; } = 1;
}

public sealed class AppSettings
{
    public string ActiveSubscriptionId { get; set; } = string.Empty;
    public List<Subscription> Subscriptions { get; set; } = [];
    public RouteMode RouteMode { get; set; } = RouteMode.Smart;
    public List<RouteRule> RouteRules { get; set; } = [];
    public bool AutoReconnect { get; set; } = true;
    public bool DiscordVpn { get; set; } = true;
    public bool SteamWebHelperVpn { get; set; }
    public bool BlockedRuVpn { get; set; } = true;
    public string Theme { get; set; } = "System";
    public string SingBoxPath { get; set; } = string.Empty;
    public string XrayPath { get; set; } = string.Empty;
}

public sealed class NodeModel : INotifyPropertyChanged
{
    private bool _isValid = true;
    private bool _udpOk;
    private double? _latencyMs;
    private double _score = -999999;
    private string _testStatus = "Не проверен";
    private string _error = string.Empty;

    public required string Name { get; init; }
    public required string Protocol { get; init; }
    public required string Server { get; init; }
    public required int Port { get; init; }
    public required JsonObject Outbound { get; init; }
    public string Source { get; init; } = string.Empty;
    public string Transport { get; init; } = string.Empty;
    public string Security { get; init; } = string.Empty;
    public string Engine { get; init; } = "sing-box";
    public IReadOnlyDictionary<string, string> Query { get; init; } = new Dictionary<string, string>();

    public bool IsValid
    {
        get => _isValid;
        set => SetField(ref _isValid, value);
    }

    public bool UdpOk
    {
        get => _udpOk;
        set => SetField(ref _udpOk, value);
    }

    public double? LatencyMs
    {
        get => _latencyMs;
        set
        {
            if (SetField(ref _latencyMs, value))
            {
                OnPropertyChanged(nameof(LatencyText));
            }
        }
    }

    public double Score
    {
        get => _score;
        set => SetField(ref _score, value);
    }

    public string TestStatus
    {
        get => _testStatus;
        set => SetField(ref _testStatus, value);
    }

    public string Error
    {
        get => _error;
        set => SetField(ref _error, value);
    }

    public string DisplayServer => $"{Server}:{Port}";
    public string LatencyText => LatencyMs is null ? "—" : $"{LatencyMs:0} ms";
    public string UdpText => UdpOk ? "YES" : "NO";

    public string StackLabel
    {
        get
        {
            if (Protocol.Equals("hysteria2", StringComparison.OrdinalIgnoreCase)) return "HYSTERIA2";
            if (Protocol.Equals("tuic", StringComparison.OrdinalIgnoreCase)) return "TUIC";
            if (Protocol.Equals("shadowsocks", StringComparison.OrdinalIgnoreCase)) return "SHADOWSOCKS";

            var parts = new List<string> { Protocol.ToUpperInvariant() };
            if (!string.IsNullOrWhiteSpace(Transport) && Transport is not "raw" and not "tcp" and not "none")
            {
                parts.Add(Transport.ToLowerInvariant() switch
                {
                    "ws" or "websocket" => "WS",
                    "grpc" => "gRPC",
                    "xhttp" => "XHTTP",
                    "httpupgrade" or "http-upgrade" => "HTTPUpgrade",
                    "h2" => "HTTP/2",
                    _ => Transport.ToUpperInvariant(),
                });
            }

            if (!string.IsNullOrWhiteSpace(Security) && !Security.Equals("none", StringComparison.OrdinalIgnoreCase))
            {
                parts.Add(Security.ToUpperInvariant());
            }

            return string.Join(" + ", parts);
        }
    }

    public event PropertyChangedEventHandler? PropertyChanged;

    private bool SetField<T>(ref T field, T value, [CallerMemberName] string? propertyName = null)
    {
        if (EqualityComparer<T>.Default.Equals(field, value)) return false;
        field = value;
        OnPropertyChanged(propertyName);
        return true;
    }

    private void OnPropertyChanged([CallerMemberName] string? propertyName = null) =>
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(propertyName));
}
