using STranslate.Core;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
using System.Windows;
using System.Windows.Automation;

namespace STranslate.Helpers;

/// <summary>触发时读取来源快照；不会在翻译完成时猜测用户原来的窗口。</summary>
internal static class StudySourceCapture
{
    [DllImport("user32.dll")] private static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] private static extern int GetWindowText(IntPtr window, StringBuilder text, int count);
    [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr window, out uint processId);

    public static StudySource Capture(string kind, string? selectedText = null)
    {
        try
        {
            var window = GetForegroundWindow();
            GetWindowThreadProcessId(window, out var processId);
            using var process = Process.GetProcessById((int)processId);
            if (process.Id == Environment.ProcessId) return StudySource.Unknown(kind);
            var title = new StringBuilder(1024);
            GetWindowText(window, title, title.Capacity);
            string? url = null;
            if (selectedText != null && Clipboard.ContainsText() &&
                StudyLibrary.Normalize(Clipboard.GetText()) == StudyLibrary.Normalize(selectedText))
            {
                url = StudySource.FromClipboardHtml(Clipboard.GetData(DataFormats.Html) as string);
            }
            if (url == null && process.ProcessName is "msedge" or "chrome" or "firefox")
            {
                // 仅查看已识别浏览器的地址栏，不读取浏览历史或后台标签页。
                var root = AutomationElement.FromHandle(window);
                var names = new[] { "Address and search bar", "地址和搜索栏", "Search or enter address", "搜索或输入 Web 地址", "搜索或输入网址" };
                foreach (var name in names)
                {
                    var element = root.FindFirst(TreeScope.Descendants,
                        new AndCondition(new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.Edit),
                            new PropertyCondition(AutomationElement.NameProperty, name)));
                    if (element?.TryGetCurrentPattern(ValuePattern.Pattern, out var value) == true)
                    {
                        url = StudySource.SafeUrl(((ValuePattern)value).Current.Value);
                        if (url != null) break;
                    }
                }
            }
            return new StudySource(kind, title.Length > 0 ? title.ToString() : "未获取来源", process.ProcessName, url);
        }
        catch
        {
            // 取不到来源不能阻断翻译，也不能继承上一条的来源。
            return StudySource.Unknown(kind);
        }
    }
}
