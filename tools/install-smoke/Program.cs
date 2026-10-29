using Microsoft.Extensions.Logging.Abstractions;
using STranslate.Core;
using STranslate.Plugin;

internal static class Program
{
    [STAThread]
    private static int Main()
    {
        // 只在解压出的测试副本中执行，不显示窗口、不注册热键、不调用翻译服务。
        var settings = new AppStorage<Settings>().Load();
        if (settings.StudyLibraryCloudSyncEnabled || settings.EnableExternalCall || settings.AutoCheckUpdate)
            throw new InvalidOperationException("Blank profile must default to local-only");
        using var manager = new PluginManager(NullLogger<PluginManager>.Instance);
        manager.LoadPlugins();
        var plugins = manager.AllPluginMetaDatas.ToList();
        if (plugins.Count != 3 || !plugins.Any(p => p.PluginID == "a93ccba0c4144fefa471ac7b9a87bc23"))
            throw new InvalidOperationException("Expected three bundled plugins");
        var services = new AppStorage<ServiceSettings>().Load();
        if (services.TranSvcDatas.Any(s => s.IsEnabled) || services.OcrSvcDatas.Count != 1 || !services.OcrSvcDatas[0].IsEnabled)
            throw new InvalidOperationException("Unexpected network or OCR defaults");
        foreach (var metadata in plugins)
        {
            var records = typeof(IOcrPlugin).IsAssignableFrom(metadata.PluginType) ? services.OcrSvcDatas : services.TranSvcDatas;
            var found = records.Where(s => System.IO.File.Exists(System.IO.Path.Combine(metadata.PluginSettingsDirectoryPath, s.SvcID + ".json"))).ToList();
            if (found.Count != 1) throw new InvalidOperationException("Service settings path mismatch: " + metadata.Name);
            using var plugin = metadata.CreatePluginService();
            plugin.Init(new PluginContext(metadata, found[0].SvcID));
            Console.WriteLine("PASS loaded and initialized " + metadata.Name);
        }
        Console.WriteLine("PASS blank settings: cloud disabled, translations disabled, local OCR enabled");
        return 0;
    }
}
