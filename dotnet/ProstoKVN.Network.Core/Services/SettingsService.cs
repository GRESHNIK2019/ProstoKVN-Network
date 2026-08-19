using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using ProstoKVN.Network.Core.Models;

namespace ProstoKVN.Network.Core.Services;

public sealed class SettingsService
{
    private readonly JsonSerializerOptions _jsonOptions = new()
    {
        WriteIndented = true,
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        Converters = { new JsonStringEnumConverter(JsonNamingPolicy.CamelCase) },
    };

    public SettingsService(string? baseDirectory = null)
    {
        BaseDirectory = baseDirectory ?? Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "ProstoKVN Network");
        SettingsPath = Path.Combine(BaseDirectory, "settings.json");
    }

    public string BaseDirectory { get; }
    public string SettingsPath { get; }
    public string RuntimeDirectory => Path.Combine(BaseDirectory, "runtime");
    public string CoresDirectory => Path.Combine(BaseDirectory, "cores");

    public async Task<AppSettings> LoadAsync(CancellationToken cancellationToken = default)
    {
        Directory.CreateDirectory(BaseDirectory);
        var data = await ReadAsync(SettingsPath, cancellationToken)
            ?? await ReadAsync(SettingsPath + ".bak", cancellationToken)
            ?? new AppSettings();

        EnsureDefaults(data);
        return data;
    }

    public async Task SaveAsync(AppSettings settings, CancellationToken cancellationToken = default)
    {
        EnsureDefaults(settings);
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
        return Convert.ToBase64String(protectedBytes);
    }

    public string UnprotectSecret(string value)
    {
        if (string.IsNullOrWhiteSpace(value)) return string.Empty;
        try
        {
            var protectedBytes = Convert.FromBase64String(value);
            var plain = ProtectedData.Unprotect(protectedBytes, null, DataProtectionScope.CurrentUser);
            return Encoding.UTF8.GetString(plain);
        }
        catch
        {
            // Совместимость с ранними C# dev-сборками: если значение ещё не DPAPI,
            // возвращаем его как есть, чтобы пользователь не потерял подписку.
            return value;
        }
    }

    private async Task<AppSettings?> ReadAsync(string path, CancellationToken cancellationToken)
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

    private static void EnsureDefaults(AppSettings settings)
    {
        if (settings.Subscriptions.Count == 0)
        {
            settings.Subscriptions.Add(new Subscription { Name = "import_sub" });
        }

        if (string.IsNullOrWhiteSpace(settings.ActiveSubscriptionId)
            || settings.Subscriptions.All(x => x.Id != settings.ActiveSubscriptionId))
        {
            settings.ActiveSubscriptionId = settings.Subscriptions[0].Id;
        }

        settings.RouteRules ??= [];
    }
}
