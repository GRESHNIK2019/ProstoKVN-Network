using Microsoft.UI.Xaml;
using ProstoKVN.Network.App.ViewModels;
using ProstoKVN.Network.Core.Services;

namespace ProstoKVN.Network.App;

public partial class App : Application
{
    private Window? _window;

    public App()
    {
        InitializeComponent();
    }

    protected override void OnLaunched(LaunchActivatedEventArgs args)
    {
        var settings = new SettingsService();
        var routing = new RoutingConfigService();
        var xrayConfig = new XrayConfigService();
        var cores = new CoreLocatorService(settings);
        var installer = new CoreInstallerService(settings);
        var subscriptions = new SubscriptionService(settings);
        var nodeTester = new NodeTestService(settings, xrayConfig);
        var vpn = new VpnSessionService(settings, routing, xrayConfig);

        var viewModel = new MainViewModel(
            settings,
            subscriptions,
            cores,
            installer,
            nodeTester,
            vpn);

        _window = new MainWindow(viewModel);
        _window.Activate();
    }
}
