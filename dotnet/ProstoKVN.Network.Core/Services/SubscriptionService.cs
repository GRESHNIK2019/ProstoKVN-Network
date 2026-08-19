using ProstoKVN.Network.Core.Models;

namespace ProstoKVN.Network.Core.Services;

public sealed class SubscriptionService(SettingsService settingsService, HttpClient? httpClient = null)
{
    private readonly HttpClient _httpClient = httpClient ?? new HttpClient
    {
        Timeout = TimeSpan.FromSeconds(25),
        DefaultRequestHeaders = { UserAgent = { new System.Net.Http.Headers.ProductInfoHeaderValue("ProstoKVN-Network", "1.0") } },
    };

    public async Task<IReadOnlyList<NodeModel>> DownloadNodesAsync(Subscription subscription, CancellationToken cancellationToken = default)
    {
        if (!subscription.Enabled) return [];
        var url = settingsService.UnprotectSecret(subscription.ProtectedUrl).Trim();
        if (url.Length == 0) return [];
        if (!Uri.TryCreate(url, UriKind.Absolute, out var uri) || uri.Scheme is not ("http" or "https"))
            throw new InvalidOperationException("Некорректный URL подписки");

        using var response = await _httpClient.GetAsync(uri, HttpCompletionOption.ResponseHeadersRead, cancellationToken);
        response.EnsureSuccessStatusCode();
        var payload = await response.Content.ReadAsStringAsync(cancellationToken);
        var nodes = NodeParser.ParsePayload(payload);
        if (nodes.Count == 0) throw new InvalidOperationException("В подписке не найдено поддерживаемых узлов");
        return nodes;
    }
}
