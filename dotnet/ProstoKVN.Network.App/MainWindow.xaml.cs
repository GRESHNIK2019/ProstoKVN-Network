using Microsoft.UI.Composition.SystemBackdrops;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using ProstoKVN.Network.App.ViewModels;

namespace ProstoKVN.Network.App;

public sealed partial class MainWindow : Window
{
    private readonly DispatcherTimer _watchdog = new() { Interval = TimeSpan.FromSeconds(2) };
    private SettingsWindow? _settingsWindow;
    private SubscriptionsWindow? _subscriptionsWindow;

    public MainWindow(MainViewModel viewModel)
    {
        ViewModel = viewModel;
        InitializeComponent();
        Title = "ProstoKVN Network";
        try
        {
            SystemBackdrop = new MicaBackdrop { Kind = MicaKind.BaseAlt };
            AppWindow.Resize(new Windows.Graphics.SizeInt32(1380, 840));
        }
        catch
        {
            // На старых сборках Windows останется обычный фон приложения.
        }

        _watchdog.Tick += async (_, _) => await ViewModel.CheckRunnerHealthAsync();
        Closed += OnClosed;
    }

    public MainViewModel ViewModel { get; }

    private async void OnLoaded(object sender, RoutedEventArgs e)
    {
        await ViewModel.InitializeAsync();
        _watchdog.Start();
    }

    private void OnSettingsClicked(object sender, RoutedEventArgs e)
    {
        if (_settingsWindow is not null)
        {
            try { _settingsWindow.Activate(); return; } catch { _settingsWindow = null; }
        }
        _settingsWindow = new SettingsWindow(ViewModel);
        _settingsWindow.Closed += (_, _) => _settingsWindow = null;
        _settingsWindow.Activate();
    }

    private void OnSubscriptionsClicked(object sender, RoutedEventArgs e)
    {
        if (_subscriptionsWindow is not null)
        {
            try { _subscriptionsWindow.Activate(); return; } catch { _subscriptionsWindow = null; }
        }
        _subscriptionsWindow = new SubscriptionsWindow(ViewModel);
        _subscriptionsWindow.Closed += (_, _) => _subscriptionsWindow = null;
        _subscriptionsWindow.Activate();
    }

    private async void OnHelpClicked(object sender, RoutedEventArgs e)
    {
        var dialog = new ContentDialog
        {
            XamlRoot = RootGrid.XamlRoot,
            Title = "ProstoKVN Network — C# / WinUI 3",
            Content = "Полная новая версия клиента на .NET 10 и WinUI 3. VPN-ядра по-прежнему используются официальные: sing-box и Xray-core.",
            CloseButtonText = "Закрыть",
        };
        await dialog.ShowAsync();
    }

    private void OnClearLogClicked(object sender, RoutedEventArgs e) => ViewModel.LogLines.Clear();

    private async void OnClosed(object sender, WindowEventArgs args)
    {
        _watchdog.Stop();
        if (ViewModel.IsRunning)
            await ViewModel.StopVpnCommand.ExecuteAsync(null);
    }
}
