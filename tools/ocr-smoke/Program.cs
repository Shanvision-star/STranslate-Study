using System.Globalization;
using System.IO;
using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using STranslate.Plugin;

internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        if (args.Length != 1) throw new ArgumentException("请传入固定版本 OCR 模型目录");
        var target = Path.Combine(AppContext.BaseDirectory, "tessdata");
        Directory.CreateDirectory(target);
        foreach (var language in new[] { "eng", "spa", "chi_sim" })
            File.Copy(Path.Combine(args[0], language + ".traineddata"), Path.Combine(target, language + ".traineddata"), true);
        // 合成菜单图片只验证本机 OCR 引擎、原生库和模型，不代表实际桌面框选。
        var visual = new DrawingVisual();
        using (var dc = visual.RenderOpen())
        {
            dc.DrawRectangle(Brushes.White, null, new Rect(0, 0, 1000, 180));
            dc.DrawText(new FormattedText("Preferences Settings Translate", CultureInfo.InvariantCulture, FlowDirection.LeftToRight,
                new Typeface("Arial"), 42, Brushes.Black, 1), new Point(24, 50));
        }
        var bitmap = new RenderTargetBitmap(1000, 180, 96, 96, PixelFormats.Pbgra32);
        bitmap.Render(visual);
        var encoder = new PngBitmapEncoder(); encoder.Frames.Add(BitmapFrame.Create(bitmap));
        using var stream = new MemoryStream(); encoder.Save(stream);
        using var plugin = new STranslate.Plugin.Ocr.Tesseract.Main();
        foreach (var language in new[] { LangEnum.English, LangEnum.Auto })
        {
            var result = plugin.RecognizeAsync(new OcrRequest(stream.ToArray(), language), CancellationToken.None).GetAwaiter().GetResult();
            var text = string.Join(" ", result.OcrContents.Select(c => c.Text));
            if (!text.Contains("Settings", StringComparison.OrdinalIgnoreCase) || !text.Contains("Translate", StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException("OCR 回读与合成图片不匹配：" + text);
            if (!result.OcrContents.Any(c => c.BoxPoints.Count == 4)) throw new InvalidOperationException("缺少截图坐标");
            Console.WriteLine($"PASS {language}: {text}");
        }
        return 0;
    }
}
