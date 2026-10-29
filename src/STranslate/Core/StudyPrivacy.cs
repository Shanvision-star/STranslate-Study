using System.Net;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace STranslate.Core;

/// <summary>学习库的本地隐私边界：不保存指定机构内容，不保留窗口身份信息。</summary>
public static class StudyPrivacy
{
    public sealed record Rule(int Length, string Sha256);
    public sealed record Policy(List<Rule> BlockedFingerprints);

    public static IReadOnlyList<Rule> LoadRules(string path)
    {
        if (!File.Exists(path)) return [];
        var policy = JsonSerializer.Deserialize<Policy>(File.ReadAllText(path))
            ?? throw new InvalidDataException("隐私配置为空，请重新运行学习助手设置。");
        if (policy.BlockedFingerprints == null || policy.BlockedFingerprints.Any(r => r.Length is < 1 or > 128 || !Regex.IsMatch(r.Sha256 ?? "", "^[a-fA-F0-9]{64}$")))
            throw new InvalidDataException("隐私规则格式错误，请重新运行学习助手设置。");
        return policy.BlockedFingerprints;
    }

    public static bool Restricted(string? value, IReadOnlyList<Rule>? rules = null)
    {
        var text = Uri.UnescapeDataString(value ?? "").Normalize(NormalizationForm.FormKC).ToLowerInvariant();
        var compact = Regex.Replace(text, @"[\W_]+", "");
        foreach (var rule in rules ?? [])
            for (var index = 0; index <= compact.Length - rule.Length; index++)
                if (Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(compact.Substring(index, rule.Length))))
                    .Equals(rule.Sha256, StringComparison.OrdinalIgnoreCase)) return true;
        return false;
    }

    public static string Redact(string? value)
    {
        var text = value ?? "";
        string[] patterns = [@"https?://\S+", @"file:/+\S+", @"[A-Za-z]:\\[^\r\n]+", @"\\\\[^\s]+",
            @"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", @"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)",
            @"\b(?:sk|ghp|gho|github_pat)[-_][A-Za-z0-9_-]{12,}\b",
            @"\b(?:api[_ -]?key|password|token|secret)\s*[:=]\s*\S+"];
        foreach (var pattern in patterns) text = Regex.Replace(text, pattern, "[已脱敏]", RegexOptions.IgnoreCase);
        return text;
    }

    public static StudySource Source(StudySource source, IReadOnlyList<Rule>? rules = null)
    {
        string? url = null;
        if (!Restricted(source.Title, rules) && !Restricted(source.Url, rules) &&
            Uri.TryCreate(StudySource.SafeUrl(source.Url), UriKind.Absolute, out var uri) &&
            uri.Scheme is "https" or "http" && uri.Host.Contains('.') && !IPAddress.TryParse(uri.Host, out _) &&
            !uri.Host.Split('.').Any(p => new[] { "corp", "internal", "intranet", "local", "lan", "localhost" }.Contains(p)))
            url = new UriBuilder(uri) { Query = "", Fragment = "" }.Uri.AbsoluteUri;
        var app = new[] { "chrome", "msedge", "firefox", "AcroRd32", "Acrobat" }.Contains(source.Application) ? source.Application : "desktop";
        var kind = new[] { "selection", "screenshot", "screenshot_import", "clipboard", "manual" }.Contains(source.Kind) ? source.Kind : "selection";
        return new(kind, "阅读来源（标题已脱敏）", app, url);
    }

    public static IEnumerable<StudyEntry> Clean(IEnumerable<StudyEntry> entries, IReadOnlyList<Rule>? rules = null)
    {
        foreach (var entry in entries)
        {
            if (Restricted(entry.Original, rules) || Restricted(entry.Translation, rules)) continue;
            entry.Original = Redact(entry.Original);
            entry.Translation = Redact(entry.Translation);
            if (Restricted(entry.Engine, rules)) entry.Engine = "翻译服务";
            entry.SourcesJson = JsonSerializer.Serialize(entry.Sources.Select(s => Source(s, rules)));
            yield return entry;
        }
    }
}
