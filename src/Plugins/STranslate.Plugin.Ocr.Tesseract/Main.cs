using System.IO;
using System.Windows;
using System.Windows.Controls;
using global::Tesseract;

namespace STranslate.Plugin.Ocr.Tesseract;

public sealed class Main : IOcrPlugin
{
    private static readonly string PluginDirectory = Path.GetDirectoryName(typeof(Main).Assembly.Location)!;
    public IEnumerable<LangEnum> SupportedLanguages => [LangEnum.Auto, LangEnum.English, LangEnum.Spanish, LangEnum.ChineseSimplified];
    public bool SupportBoxPoints() => true;
    public string? GetLanguage(LangEnum language) => language switch
    {
        LangEnum.English => "eng",
        LangEnum.Spanish => "spa",
        LangEnum.ChineseSimplified => "chi_sim",
        LangEnum.Auto => "eng+spa+chi_sim",
        _ => null
    };
    public sealed class Settings { }
    public void Init(IPluginContext context) => context.LoadSettingStorage<Settings>();
    public void Dispose() { }
    public Control GetSettingUI() => new ContentControl
    {
        Content = new TextBlock
        {
            Text = "本机 Tesseract OCR\n支持英文、西班牙语、简体中文；截图不会由此插件联网发送。\n英文菜单建议选择英语，避免混合语言误识别。\n若提示本地 DLL 加载失败，请安装 Microsoft Visual C++ 2015–2022 x64 运行库。",
            TextWrapping = TextWrapping.Wrap, Margin = new Thickness(20)
        }
    };

    public Task<OcrResult> RecognizeAsync(OcrRequest request, CancellationToken cancellationToken) => Task.Run(() =>
    {
        cancellationToken.ThrowIfCancellationRequested();
        string language = GetLanguage(request.Language) ?? throw new NotSupportedException("本地 OCR 暂不支持此语种");
        // 每次识别独立引擎，避免截图窗口并发共享非线程安全的原生实例。
        using var engine = new TesseractEngine(Path.Combine(PluginDirectory, "tessdata"), language, EngineMode.LstmOnly);
        using var pix = Pix.LoadFromMemory(request.ImageData);
        using var page = engine.Process(pix, PageSegMode.Auto);
        using var iterator = page.GetIterator();
        var result = new OcrResult();
        iterator.Begin();
        do
        {
            cancellationToken.ThrowIfCancellationRequested();
            var text = iterator.GetText(PageIteratorLevel.TextLine)?.Trim();
            if (string.IsNullOrWhiteSpace(text)) continue;
            var item = new OcrContent { Text = text };
            if (iterator.TryGetBoundingBox(PageIteratorLevel.TextLine, out var box))
            {
                item.BoxPoints.Add(new BoxPoint(box.X1, box.Y1));
                item.BoxPoints.Add(new BoxPoint(box.X2, box.Y1));
                item.BoxPoints.Add(new BoxPoint(box.X2, box.Y2));
                item.BoxPoints.Add(new BoxPoint(box.X1, box.Y2));
            }
            result.OcrContents.Add(item);
        } while (iterator.Next(PageIteratorLevel.TextLine));
        return result;
    }, cancellationToken);
}
