using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using ProstoKVN.Network.Core.Models;
using ProstoKVN.Network.Core.Services;

namespace ProstoKVN.Network.App.ViewModels;

public partial class SubscriptionsViewModel : ObservableObject
{
    private readonly MainViewModel _main;
    private readonly SettingsService _settings = new();

    public SubscriptionsViewModel(MainViewModel main)
    {
        _main = main;
        foreach (var sub in main.Settings.Subscriptions.OrderBy(x => x.SortOrder).ThenBy(x => x.Name))
        {
            Items.Add(new SubscriptionItemViewModel
            {
                Id = sub.Id,
                Name = sub.Name,
                Url = _settings.UnprotectSecret(sub.ProtectedUrl),
                Enabled = sub.Enabled,
                UpdateIntervalMinutes = sub.UpdateIntervalMinutes,
                SortOrder = sub.SortOrder,
                IsActive = sub.Id == main.Settings.ActiveSubscriptionId,
            });
        }
        SelectedItem = Items.FirstOrDefault(x => x.IsActive) ?? Items.FirstOrDefault();
    }

    public ObservableCollection<SubscriptionItemViewModel> Items { get; } = [];

    [ObservableProperty] private SubscriptionItemViewModel? selectedItem;
    [ObservableProperty] private string status = "URL хранится через Windows DPAPI";

    [RelayCommand]
    private void Add()
    {
        var item = new SubscriptionItemViewModel
        {
            Name = "Новая подписка",
            Enabled = true,
            SortOrder = Items.Count + 1,
        };
        Items.Add(item);
        SelectedItem = item;
    }

    [RelayCommand]
    private void Delete()
    {
        if (SelectedItem is null) return;
        var index = Items.IndexOf(SelectedItem);
        Items.Remove(SelectedItem);
        if (Items.Count == 0)
            Add();
        SelectedItem = Items[Math.Clamp(index, 0, Items.Count - 1)];
    }

    [RelayCommand]
    private void MakeActive()
    {
        if (SelectedItem is null) return;
        foreach (var item in Items) item.IsActive = ReferenceEquals(item, SelectedItem);
    }

    [RelayCommand]
    private async Task SaveAsync()
    {
        if (Items.Count == 0) Add();
        var active = Items.FirstOrDefault(x => x.IsActive) ?? SelectedItem ?? Items[0];
        foreach (var item in Items) item.IsActive = ReferenceEquals(item, active);

        _main.Settings.Subscriptions = Items.Select(item => new Subscription
        {
            Id = item.Id,
            Name = string.IsNullOrWhiteSpace(item.Name) ? "Подписка" : item.Name.Trim(),
            ProtectedUrl = _settings.ProtectSecret(item.Url.Trim()),
            Enabled = item.Enabled,
            UpdateIntervalMinutes = Math.Max(0, item.UpdateIntervalMinutes),
            SortOrder = item.SortOrder,
        }).ToList();
        _main.Settings.ActiveSubscriptionId = active.Id;
        await _main.SaveSettingsAsync();
        _main.NotifySettingsChanged();
        Status = "Сохранено";
    }

    [RelayCommand]
    private async Task RefreshActiveAsync()
    {
        await SaveAsync();
        await _main.RefreshNodesCommand.ExecuteAsync(null);
        Status = "Активная подписка обновлена";
    }
}

public partial class SubscriptionItemViewModel : ObservableObject
{
    public string Id { get; init; } = Guid.NewGuid().ToString("N");
    [ObservableProperty] private string name = "import_sub";
    [ObservableProperty] private string url = string.Empty;
    [ObservableProperty] private bool enabled = true;
    [ObservableProperty] private int updateIntervalMinutes;
    [ObservableProperty] private int sortOrder = 1;
    [ObservableProperty] private bool isActive;
}
