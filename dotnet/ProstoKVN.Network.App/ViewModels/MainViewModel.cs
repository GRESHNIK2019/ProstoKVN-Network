using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using ProstoKVN.Network.Core.Models;
using ProstoKVN.Network.Core.Services;

namespace ProstoKVN.Network.App.ViewModels;

public partial class MainViewModel : ObservableObject
{
    private readonly SettingsService _settingsService;
    private readonly SubscriptionService _subscriptionService;
    private readonly CoreLocatorService _coreLocator;
    private readonly CoreInstallerService _coreInstaller;
    private readonly BlocklistService _blocklists;
    private readonly NodeTestService _nodeTester;
    private readonly VpnSessionService _vpn;
    private readonly SynchronizationContext? _uiContext;
    private bool _initialized;
    private bool _expectedRunning;
    private bool _autoReconnectAttempted;

    public MainViewModel(
        SettingsService settingsService,
        SubscriptionService subscriptionService,
        CoreLocatorService coreLocator,
        CoreInstallerService coreInstaller,
        BlocklistService blocklists,
        NodeTestService nodeTester,
        VpnSessionService vpn)
    {
        _settingsService = settingsService;
        _subscriptionService = subscriptionService;
        _coreLocator = coreLocator;
        _coreInstaller = coreInstaller;
        _blocklists = blocklists;
        _nodeTester = nodeTester;
        _vpn = vpn;
        _uiContext = SynchronizationContext.Current;
        _vpn.Log += AppendLog;
    }

    public ObservableCollection<NodeModel> Nodes { get; } = [];
    public ObservableCollection<string> LogLines { get; } = [];
    public AppSettings Settings { get; private set; } = new();
    public CorePaths Cores { get; private set; } = new(null, null);

    [ObservableProperty] private NodeModel? selectedNode;
    [ObservableProperty] private NodeModel? activeNode;
    [ObservableProperty] private bool isBusy;
    [ObservableProperty] private bool isRunning;
    [ObservableProperty] private string statusText = "Инициализация...";
    [ObservableProperty] private string filterText = string.Empty;
    [ObservableProperty] private string coreText = "Ядро: —";
    [ObservableProperty] private string blocklistStatus = "Списки: —";

    public string VersionText => "v0.22.0 · C# Preview";
    public Subscription? ActiveSubscription => Settings.Subscriptions.FirstOrDefault(x => x.Id == Settings.ActiveSubscriptionId);
    public string SubscriptionName => ActiveSubscription?.Name ?? "Подписка не выбрана";
    public string SubscriptionState => ActiveSubscription?.Enabled == true ? "Онлайн" : "Отключена";
    public string NodeName => (ActiveNode ?? SelectedNode)?.Name ?? "Узел не выбран";
    public string NodeRoute => (ActiveNode ?? SelectedNode)?.StackLabel ?? "—";
    public string LatencyText => (ActiveNode ?? SelectedNode)?.LatencyText ?? "—";
    public string UdpState => (ActiveNode ?? SelectedNode)?.UdpOk == true ? "UDP активен" : "UDP —";
    public string VpnState => IsRunning ? "VPN запущен" : "VPN остановлен";
    public string StrategyText => Settings.RouteMode switch
    {
        RouteMode.Smart => "Smart",
        RouteMode.Applications => "Приложения",
        RouteMode.Global => "Global",
        _ => "Smart",
    };

    public IEnumerable<NodeModel> FilteredNodes
    {
        get
        {
            var value = FilterText.Trim();
            if (value.Length == 0) return Nodes;
            return Nodes.Where(node =>
                node.Name.Contains(value, StringComparison.OrdinalIgnoreCase)
                || node.StackLabel.Contains(value, StringComparison.OrdinalIgnoreCase)
                || node.Server.Contains(value, StringComparison.OrdinalIgnoreCase));
        }
    }

    public async Task InitializeAsync()
    {
        if (_initialized) return;
        _initialized = true;
        Settings = await _settingsService.LoadAsync();
        Cores = _coreLocator.Find(Settings.SingBoxPath, Settings.XrayPath);
        RefreshDerivedState();
        AppendLog("[CORE] C# / WinUI 3 версия запущена");
        AppendLog(Cores.HasSingBox || Cores.HasXray
            ? $"[CORE] Найдены ядра: sing-box={(Cores.HasSingBox ? "yes" : "no")}, xray={(Cores.HasXray ? "yes" : "no")}"
            : "[CORE] Ядра пока не найдены");

        var age = await _blocklists.GetAgeAsync();
        var cached = _blocklists.GetCachedPaths();
        BlocklistStatus = cached.Count == 0
            ? "Списки: не загружены"
            : age is null ? $"Списки: {cached.Count} файлов" : $"Списки: {cached.Count} файлов · {age.Value.TotalHours:0} ч.";

        if (cached.Count == 0 || age is null || age > TimeSpan.FromHours(24))
        {
            _ = UpdateBlocklistsBackgroundAsync();
        }

        var activeSubscription = ActiveSubscription;
        if (activeSubscription is { Enabled: true } && !string.IsNullOrWhiteSpace(activeSubscription.ProtectedUrl))
            await RefreshNodesAsync();
        else
            StatusText = "Добавьте URL подписки";
    }

    [RelayCommand]
    private async Task RefreshNodesAsync()
    {
        if (IsBusy) return;
        IsBusy = true;
        StatusText = "Обновляю подписку...";
        try
        {
            await EnsureCoresAsync();
            var subscription = ActiveSubscription ?? throw new InvalidOperationException("Активная подписка не найдена");
            AppendLog($"[SUB] Загрузка: {subscription.Name}");
            var nodes = await _subscriptionService.DownloadNodesAsync(subscription);
            Nodes.Clear();
            foreach (var node in nodes) Nodes.Add(node);
            OnPropertyChanged(nameof(FilteredNodes));
            AppendLog($"[SUB] Получено узлов: {Nodes.Count}");

            StatusText = "Проверяю узлы...";
            using var semaphore = new SemaphoreSlim(4, 4);
            var tasks = Nodes.Select(async node =>
            {
                await semaphore.WaitAsync();
                try { await _nodeTester.TestAsync(node, Cores); }
                finally { semaphore.Release(); }
            }).ToArray();
            await Task.WhenAll(tasks);

            var ordered = Nodes.OrderByDescending(x => x.IsValid).ThenByDescending(x => x.Score).ToArray();
            Nodes.Clear();
            foreach (var node in ordered) Nodes.Add(node);
            OnPropertyChanged(nameof(FilteredNodes));
            SelectedNode = Nodes.FirstOrDefault(x => x.IsValid) ?? Nodes.FirstOrDefault();
            StatusText = SelectedNode is null ? "Рабочие узлы не найдены" : $"Готово · лучший узел: {SelectedNode.Name}";
            if (SelectedNode is not null) AppendLog($"[SUB] Лучший узел: {SelectedNode.Name} | {SelectedNode.LatencyText} | {(SelectedNode.UdpOk ? "UDP OK" : "UDP OFF")}");
        }
        catch (Exception ex)
        {
            StatusText = "Ошибка обновления узлов";
            AppendLog("[ERROR] " + ex.Message);
        }
        finally
        {
            IsBusy = false;
            RefreshDerivedState();
        }
    }

    [RelayCommand]
    private async Task StartVpnAsync()
    {
        if (IsBusy || SelectedNode is null || !SelectedNode.IsValid) return;
        IsBusy = true;
        try
        {
            await EnsureCoresAsync();
            StatusText = $"Запускаю VPN: {SelectedNode.Name}";
            await _vpn.StartAsync(SelectedNode, Cores, Settings, _blocklists.GetCachedPaths());
            ActiveNode = SelectedNode;
            IsRunning = _vpn.IsRunning;
            _expectedRunning = IsRunning;
            _autoReconnectAttempted = false;
            StatusText = IsRunning ? "VPN запущен" : "Не удалось подтвердить запуск VPN";
        }
        catch (Exception ex)
        {
            _expectedRunning = false;
            IsRunning = false;
            StatusText = "Ошибка запуска VPN";
            AppendLog("[ERROR] " + ex.Message);
        }
        finally
        {
            IsBusy = false;
            RefreshDerivedState();
        }
    }

    [RelayCommand]
    private async Task StopVpnAsync()
    {
        _expectedRunning = false;
        _autoReconnectAttempted = false;
        await _vpn.StopAsync();
        IsRunning = false;
        ActiveNode = null;
        StatusText = "VPN остановлен";
        RefreshDerivedState();
    }

    [RelayCommand]
    private async Task InstallCoresAsync()
    {
        if (IsBusy) return;
        IsBusy = true;
        try
        {
            var progress = new Progress<string>(message =>
            {
                StatusText = message;
                AppendLog("[CORE] " + message);
            });
            Cores = await _coreInstaller.InstallAsync(true, true, progress);
            if (Cores.HasSingBox) Settings.SingBoxPath = Cores.SingBox!;
            if (Cores.HasXray) Settings.XrayPath = Cores.Xray!;
            await _settingsService.SaveAsync(Settings);
            StatusText = "Ядра установлены";
        }
        catch (Exception ex)
        {
            StatusText = "Ошибка установки ядер";
            AppendLog("[ERROR] " + ex.Message);
        }
        finally
        {
            IsBusy = false;
            RefreshDerivedState();
        }
    }

    [RelayCommand]
    private async Task UpdateBlocklistsAsync()
    {
        try
        {
            BlocklistStatus = "Списки: обновление...";
            var progress = new Progress<string>(message => AppendLog("[LIST] " + message));
            var result = await _blocklists.UpdateAsync(progress);
            BlocklistStatus = $"Списки: {result.Paths.Count} файлов · доменов {result.DomainCount + result.ServiceDomainCount:N0}";
            AppendLog($"[LIST] Обновлено: {result.Paths.Count} файлов");
        }
        catch (Exception ex)
        {
            BlocklistStatus = "Списки: ошибка обновления";
            AppendLog("[LIST] Ошибка: " + ex.Message);
        }
    }

    public async Task SaveSettingsAsync()
    {
        await _settingsService.SaveAsync(Settings);
        RefreshDerivedState();
    }

    public async Task CheckRunnerHealthAsync()
    {
        var actuallyRunning = _vpn.IsRunning;
        if (actuallyRunning != IsRunning)
        {
            IsRunning = actuallyRunning;
            if (!actuallyRunning) ActiveNode = null;
            RefreshDerivedState();
        }

        if (_expectedRunning && !actuallyRunning && Settings.AutoReconnect && !_autoReconnectAttempted && SelectedNode is not null)
        {
            _autoReconnectAttempted = true;
            AppendLog("[WATCHDOG] VPN неожиданно остановился, выполняю одно автопереподключение");
            await StartVpnAsync();
        }
    }

    public void NotifySettingsChanged()
    {
        OnPropertyChanged(nameof(SubscriptionName));
        OnPropertyChanged(nameof(SubscriptionState));
        OnPropertyChanged(nameof(StrategyText));
        RefreshDerivedState();
    }

    partial void OnSelectedNodeChanged(NodeModel? value) => RefreshDerivedState();
    partial void OnActiveNodeChanged(NodeModel? value) => RefreshDerivedState();
    partial void OnFilterTextChanged(string value) => OnPropertyChanged(nameof(FilteredNodes));
    partial void OnIsRunningChanged(bool value) => RefreshDerivedState();

    private async Task EnsureCoresAsync()
    {
        Cores = _coreLocator.Find(Settings.SingBoxPath, Settings.XrayPath);
        if (Cores.HasSingBox && Cores.HasXray)
        {
            CoreText = "Ядра: sing-box + Xray";
            return;
        }

        var progress = new Progress<string>(message => AppendLog("[CORE] " + message));
        Cores = await _coreInstaller.InstallAsync(!Cores.HasSingBox, !Cores.HasXray, progress);
        if (Cores.HasSingBox) Settings.SingBoxPath = Cores.SingBox!;
        if (Cores.HasXray) Settings.XrayPath = Cores.Xray!;
        await _settingsService.SaveAsync(Settings);
    }

    private async Task UpdateBlocklistsBackgroundAsync()
    {
        try
        {
            await UpdateBlocklistsAsync();
        }
        catch
        {
            // Фоновое обновление не должно мешать запуску UI.
        }
    }

    private void RefreshDerivedState()
    {
        CoreText = (ActiveNode ?? SelectedNode)?.Engine switch
        {
            "xray" => "Ядро: xray",
            "sing-box" => "Ядро: sing-box",
            _ when Cores.HasXray && Cores.HasSingBox => "Ядра: sing-box + Xray",
            _ => "Ядро: —",
        };
        OnPropertyChanged(nameof(ActiveSubscription));
        OnPropertyChanged(nameof(SubscriptionName));
        OnPropertyChanged(nameof(SubscriptionState));
        OnPropertyChanged(nameof(NodeName));
        OnPropertyChanged(nameof(NodeRoute));
        OnPropertyChanged(nameof(LatencyText));
        OnPropertyChanged(nameof(UdpState));
        OnPropertyChanged(nameof(VpnState));
        OnPropertyChanged(nameof(StrategyText));
    }

    private void AppendLog(string message)
    {
        void Add()
        {
            var line = $"{DateTime.Now:HH:mm:ss}  {message}";
            LogLines.Add(line);
            while (LogLines.Count > 500) LogLines.RemoveAt(0);
        }

        if (_uiContext is null || SynchronizationContext.Current == _uiContext) Add();
        else _uiContext.Post(_ => Add(), null);
    }
}
