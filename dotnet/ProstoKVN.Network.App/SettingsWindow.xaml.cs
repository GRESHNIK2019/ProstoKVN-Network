using Microsoft.UI.Composition.SystemBackdrops;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using ProstoKVN.Network.App.ViewModels;

namespace ProstoKVN.Network.App;

public sealed partial class SettingsWindow : Window
{
    public SettingsWindow(MainViewModel mainViewModel)
    {
        ViewModel = new SettingsViewModel(mainViewModel);
        InitializeComponent();
        Title = "Настройки — ProstoKVN Network";
        try
        {
            SystemBackdrop = new MicaBackdrop { Kind = MicaKind.BaseAlt };
            AppWindow.Resize(new Windows.Graphics.SizeInt32(1040, 720));
        }
        catch { }

        if (SettingsNav.MenuItems.Count > 0)
            SettingsNav.SelectedItem = SettingsNav.MenuItems[0];
    }

    public SettingsViewModel ViewModel { get; }

    private void OnNavigationChanged(NavigationView sender, NavigationViewSelectionChangedEventArgs args)
    {
        var tag = (args.SelectedItemContainer?.Tag as string) ?? "general";
        GeneralPage.Visibility = tag == "general" ? Visibility.Visible : Visibility.Collapsed;
        RoutingPage.Visibility = tag == "routing" ? Visibility.Visible : Visibility.Collapsed;
        CoresPage.Visibility = tag == "cores" ? Visibility.Visible : Visibility.Collapsed;
    }
}
