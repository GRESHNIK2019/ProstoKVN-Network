using Microsoft.UI.Composition.SystemBackdrops;
using Microsoft.UI.Xaml;
using ProstoKVN.Network.App.ViewModels;

namespace ProstoKVN.Network.App;

public sealed partial class SubscriptionsWindow : Window
{
    public SubscriptionsWindow(MainViewModel mainViewModel)
    {
        ViewModel = new SubscriptionsViewModel(mainViewModel);
        InitializeComponent();
        Title = "Группы подписок — ProstoKVN Network";
        try
        {
            SystemBackdrop = new MicaBackdrop { Kind = MicaKind.BaseAlt };
            AppWindow.Resize(new Windows.Graphics.SizeInt32(1120, 680));
        }
        catch
        {
            // На старых версиях Windows используем обычный фон WinUI.
        }
    }

    public SubscriptionsViewModel ViewModel { get; }
}
