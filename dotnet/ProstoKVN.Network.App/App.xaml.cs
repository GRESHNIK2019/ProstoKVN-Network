using System.Runtime.InteropServices;
using Microsoft.UI.Xaml;
using ProstoKVN.Network.App.ViewModels;
using ProstoKVN.Network.Core.Services;

namespace ProstoKVN.Network.App;

public partial class App : Application
{
    private Window? _window;
    private static readonly string StartupLogPath = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "ProstoKVN Network",
        "startup.log");

    public App()
    {
        WriteStartupLog("App constructor: begin");
        UnhandledException += (_, e) =>
        {
            WriteStartupLog("UnhandledException: " + e.Exception);
        };

        try
        {
            InitializeComponent();
            WriteStartupLog("App constructor: XAML initialized");
        }
        catch (Exception ex)
        {
            FatalStartup("Не удалось инициализировать WinUI/XAML.", ex);
            throw;
        }
    }

    protected override void OnLaunched(LaunchActivatedEventArgs args)
    {
        WriteStartupLog("OnLaunched: begin");
        try
        {
            var settings = new SettingsService();
            WriteStartupLog("SettingsService: OK");
            var routing = new RoutingConfigService();
            var xrayConfig = new XrayConfigService();
            var cores = new CoreLocatorService(settings);
            var installer = new CoreInstallerService(settings);
            var blocklists = new BlocklistService(settings);
            var subscriptions = new SubscriptionService(settings);
            var nodeTester = new NodeTestService(settings, xrayConfig);
            var vpn = new VpnSessionService(settings, routing, xrayConfig);
            WriteStartupLog("Core services: OK");

            var viewModel = new MainViewModel(
                settings,
                subscriptions,
                cores,
                installer,
                blocklists,
                nodeTester,
                vpn);
            WriteStartupLog("MainViewModel: OK");

            _window = new MainWindow(viewModel);
            WriteStartupLog("MainWindow: created");
            _window.Activate();
            WriteStartupLog("MainWindow: activated");
        }
        catch (Exception ex)
        {
            FatalStartup("ProstoKVN Network не смог запуститься.", ex);
            throw;
        }
    }

    private static void FatalStartup(string title, Exception exception)
    {
        WriteStartupLog("FATAL: " + exception);
        var message =
            $"{title}\n\n{exception.GetType().Name}: {exception.Message}\n\n" +
            $"Диагностика записана в:\n{StartupLogPath}";
        try
        {
            MessageBoxW(IntPtr.Zero, message, "ProstoKVN Network — ошибка запуска", 0x00000010);
        }
        catch
        {
            // Если user32 недоступен, ошибка всё равно останется в startup.log.
        }
    }

    private static void WriteStartupLog(string message)
    {
        try
        {
            var directory = Path.GetDirectoryName(StartupLogPath);
            if (!string.IsNullOrWhiteSpace(directory)) Directory.CreateDirectory(directory);
            File.AppendAllText(
                StartupLogPath,
                $"{DateTime.Now:yyyy-MM-dd HH:mm:ss.fff}  {message}{Environment.NewLine}");
        }
        catch
        {
            // Логирование никогда не должно мешать запуску приложения.
        }
    }

    [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern int MessageBoxW(IntPtr hWnd, string text, string caption, uint type);
}
