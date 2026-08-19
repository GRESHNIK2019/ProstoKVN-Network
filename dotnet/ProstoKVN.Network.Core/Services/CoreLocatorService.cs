namespace ProstoKVN.Network.Core.Services;

public sealed record CorePaths(string? SingBox, string? Xray)
{
    public bool HasSingBox => !string.IsNullOrWhiteSpace(SingBox) && File.Exists(SingBox);
    public bool HasXray => !string.IsNullOrWhiteSpace(Xray) && File.Exists(Xray);
}

public sealed class CoreLocatorService(SettingsService settings)
{
    public CorePaths Find(string? configuredSingBox = null, string? configuredXray = null)
    {
        var singCandidates = new[]
        {
            configuredSingBox,
            Path.Combine(settings.CoresDirectory, "sing-box", "sing-box.exe"),
            Path.Combine(settings.CoresDirectory, "sing-box.exe"),
            Path.Combine(AppContext.BaseDirectory, "cores", "sing-box", "sing-box.exe"),
            Path.Combine(AppContext.BaseDirectory, "sing-box.exe"),
        };
        var xrayCandidates = new[]
        {
            configuredXray,
            Path.Combine(settings.CoresDirectory, "xray", "xray.exe"),
            Path.Combine(settings.CoresDirectory, "xray.exe"),
            Path.Combine(AppContext.BaseDirectory, "cores", "xray", "xray.exe"),
            Path.Combine(AppContext.BaseDirectory, "xray.exe"),
        };
        return new CorePaths(FirstExisting(singCandidates), FirstExisting(xrayCandidates));
    }

    private static string? FirstExisting(IEnumerable<string?> paths)
    {
        foreach (var path in paths)
        {
            if (string.IsNullOrWhiteSpace(path)) continue;
            try
            {
                var full = Path.GetFullPath(Environment.ExpandEnvironmentVariables(path));
                if (File.Exists(full)) return full;
            }
            catch
            {
                // Игнорируем некорректный пользовательский путь.
            }
        }
        return null;
    }
}
