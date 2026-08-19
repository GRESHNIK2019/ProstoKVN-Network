using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using ProstoKVN.Network.Core.Models;
using ProstoKVN.Network.Core.Services;

namespace ProstoKVN.Network.App.ViewModels;

public partial class SettingsViewModel : ObservableObject
{
    private readonly MainViewModel _main;

    public SettingsViewModel(MainViewModel main)
    {
        _main = main;
        var settings = main.Settings;
        selectedRouteMode = settings.RouteMode switch
        {
            RouteMode.Applications => "Приложения",
            RouteMode.Global => "Global",
            _ => "Smart",
        };
        autoReconnect = settings.AutoReconnect;
        singBoxPath = settings.SingBoxPath;
        xrayPath = settings.XrayPath;
        theme = settings.Theme;
        foreach (var rule in RoutingConfigService.NormalizeRouteRules(settings.RouteRules))
            Rules.Add(RouteRuleItemViewModel.FromModel(rule));
    }

    public IReadOnlyList<string> RouteModes { get; } = ["Smart", "Приложения", "Global"];
    public IReadOnlyList<string> RuleTypes { get; } = ["Приложение", "Домен", "IP / подсеть"];
    public IReadOnlyList<string> RuleActions { get; } = ["VPN", "DIRECT", "BLOCK"];
    public IReadOnlyList<string> Themes { get; } = ["System", "Dark", "Light"];
    public ObservableCollection<RouteRuleItemViewModel> Rules { get; } = [];

    [ObservableProperty] private string selectedRouteMode;
    [ObservableProperty] private bool autoReconnect;
    [ObservableProperty] private string singBoxPath;
    [ObservableProperty] private string xrayPath;
    [ObservableProperty] private string theme;
    [ObservableProperty] private RouteRuleItemViewModel? selectedRule;
    [ObservableProperty] private string saveStatus = "Изменения ещё не сохранены";

    [RelayCommand]
    private void AddRule()
    {
        var item = new RouteRuleItemViewModel { Type = "Приложение", Action = "VPN", Value = string.Empty };
        Rules.Add(item);
        SelectedRule = item;
    }

    [RelayCommand]
    private void RemoveRule()
    {
        if (SelectedRule is null) return;
        Rules.Remove(SelectedRule);
        SelectedRule = Rules.LastOrDefault();
    }

    [RelayCommand]
    private async Task SaveAsync()
    {
        ApplyToSettings();
        await _main.SaveSettingsAsync();
        _main.NotifySettingsChanged();
        SaveStatus = "Сохранено";
    }

    [RelayCommand]
    private async Task ApplyToVpnAsync()
    {
        var wasRunning = _main.IsRunning;
        await SaveAsync();
        if (wasRunning)
        {
            await _main.StopVpnCommand.ExecuteAsync(null);
            await _main.StartVpnCommand.ExecuteAsync(null);
            SaveStatus = "Сохранено и применено к VPN";
        }
    }

    [RelayCommand]
    private async Task InstallCoresAsync()
    {
        await _main.InstallCoresCommand.ExecuteAsync(null);
        SingBoxPath = _main.Settings.SingBoxPath;
        XrayPath = _main.Settings.XrayPath;
        SaveStatus = _main.CoreText;
    }

    [RelayCommand]
    private async Task UpdateBlocklistsAsync()
    {
        await _main.UpdateBlocklistsCommand.ExecuteAsync(null);
        SaveStatus = _main.BlocklistStatus;
    }

    private void ApplyToSettings()
    {
        var settings = _main.Settings;
        settings.RouteMode = SelectedRouteMode switch
        {
            "Приложения" => RouteMode.Applications,
            "Global" => RouteMode.Global,
            _ => RouteMode.Smart,
        };
        settings.AutoReconnect = AutoReconnect;
        settings.SingBoxPath = SingBoxPath.Trim();
        settings.XrayPath = XrayPath.Trim();
        settings.Theme = Theme;
        settings.RouteRules = Rules
            .Where(x => !string.IsNullOrWhiteSpace(x.Value))
            .Select(x => x.ToModel())
            .ToList();
        settings.RouteRules = RoutingConfigService.NormalizeRouteRules(settings.RouteRules).ToList();
    }
}

public partial class RouteRuleItemViewModel : ObservableObject
{
    [ObservableProperty] private string type = "Приложение";
    [ObservableProperty] private string value = string.Empty;
    [ObservableProperty] private string action = "VPN";

    public RouteRule ToModel() => new()
    {
        Type = Type switch
        {
            "Домен" => RouteRuleType.DomainSuffix,
            "IP / подсеть" => RouteRuleType.IpCidr,
            _ => RouteRuleType.Process,
        },
        Value = Value,
        Action = Action switch
        {
            "DIRECT" => RouteAction.Direct,
            "BLOCK" => RouteAction.Block,
            _ => RouteAction.Proxy,
        },
    };

    public static RouteRuleItemViewModel FromModel(RouteRule rule) => new()
    {
        Type = rule.Type switch
        {
            RouteRuleType.DomainSuffix => "Домен",
            RouteRuleType.IpCidr => "IP / подсеть",
            _ => "Приложение",
        },
        Value = rule.Value,
        Action = rule.Action switch
        {
            RouteAction.Direct => "DIRECT",
            RouteAction.Block => "BLOCK",
            _ => "VPN",
        },
    };
}
