using Dapper;
using Microsoft.Data.Sqlite;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace STranslate.Core;

/// <summary>与可淘汰的翻译缓存分离的个人学习库，保留来源和同步版本。</summary>
public sealed class StudyLibrary(string directory)
{
    public string DirectoryPath { get; } = directory;
    public string DatabasePath => Path.Combine(DirectoryPath, "study.db");
    private IReadOnlyList<StudyPrivacy.Rule> PrivacyRules => StudyPrivacy.LoadRules(Path.Combine(Path.GetDirectoryName(DirectoryPath) ?? DirectoryPath, "Settings", "StudyPrivacy.json"));
    public bool IsRestricted(string? text) => StudyPrivacy.Restricted(text, PrivacyRules);

    public static string Normalize(string value) => Regex.Replace(value.Trim().Normalize(), @"\s+", " ");
    public static string LanguageCode(string? language) => language?.ToLowerInvariant() switch
    {
        "english" or "en" => "en",
        "spanish" or "es" => "es",
        "chinesesimplified" or "zh" or "zh-cn" => "zh-CN",
        _ => language ?? "unknown"
    };

    public static string EntryKey(string text, string language, string target) =>
        Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(
            LanguageCode(language) + "\n" + LanguageCode(target) + "\n" + Normalize(text).ToLowerInvariant()))).ToLowerInvariant();

    private async Task<SqliteConnection> OpenAsync()
    {
        Directory.CreateDirectory(DirectoryPath);
        var connection = new SqliteConnection(new SqliteConnectionStringBuilder
        {
            DataSource = DatabasePath, DefaultTimeout = 10
        }.ToString());
        await connection.OpenAsync();
        await connection.ExecuteAsync("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS StudyEntries (
              EntryKey TEXT PRIMARY KEY, Language TEXT NOT NULL, TargetLanguage TEXT NOT NULL,
              Original TEXT NOT NULL, Translation TEXT NOT NULL, Engine TEXT NOT NULL,
              FirstSeenUtc TEXT NOT NULL, LastSeenUtc TEXT NOT NULL, LookupCount INTEGER NOT NULL,
              SourcesJson TEXT NOT NULL, Revision INTEGER NOT NULL, SyncedRevision INTEGER NOT NULL DEFAULT 0,
              LearningState TEXT NOT NULL DEFAULT 'new', CloudSyncAllowed INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS StudyEvents (
              EventId TEXT PRIMARY KEY, EntryKey TEXT NOT NULL, CreatedUtc TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS SyncBatches (
              BatchId TEXT PRIMARY KEY, Language TEXT NOT NULL, Destination TEXT NOT NULL,
              Payload TEXT NOT NULL, RevisionsJson TEXT NOT NULL, Status TEXT NOT NULL,
              CreatedUtc TEXT NOT NULL, VerifiedUtc TEXT, RemoteEvidence TEXT);
            """);
        using var migration = connection.BeginTransaction();
        var columns = await connection.QueryAsync<string>("SELECT name FROM pragma_table_info('StudyEntries')", transaction: migration);
        if (!columns.Contains("CloudSyncAllowed"))
            await connection.ExecuteAsync("ALTER TABLE StudyEntries ADD COLUMN CloudSyncAllowed INTEGER NOT NULL DEFAULT 0", transaction: migration);
        migration.Commit();
        return connection;
    }

    /// <summary>只接受成功结果；事件号防重复回调，文本键合并重复查询。</summary>
    public async Task<bool> SaveAsync(HistoryModel history, StudySource source, string eventId,
        Func<bool>? stillCurrent = null, bool allowCloudSync = false)
    {
        var data = history.Data.FirstOrDefault(d => d.TransResult is { IsSuccess: true } r && !string.IsNullOrWhiteSpace(r.Text));
        string? translation = data?.TransResult?.Text;
        if (data == null)
        {
            data = history.Data.FirstOrDefault(d => d.DictResult != null &&
                d.DictResult.ResultType is not Plugin.DictionaryResultType.None and not Plugin.DictionaryResultType.Error &&
                !string.IsNullOrWhiteSpace(d.DictResult.Text));
            translation = data?.DictResult?.Text;
        }
        if (string.IsNullOrWhiteSpace(history.SourceText) || string.IsNullOrWhiteSpace(translation)) return false;
        var rules = PrivacyRules;
        if (StudyPrivacy.Restricted(history.SourceText, rules) || StudyPrivacy.Restricted(translation, rules)) return false;
        var original = StudyPrivacy.Redact(history.SourceText).Trim();
        translation = StudyPrivacy.Redact(translation).Trim();
        var language = LanguageCode(history.EffectiveSourceLang ?? history.SourceLang);
        if (!history.StudyLanguageVerified) language = "und";
        if (language != "en" && language != "es" && language != "und") return false;
        var target = LanguageCode(history.EffectiveTargetLang ?? history.TargetLang);
        var key = EntryKey(original, language, target);
        var now = DateTimeOffset.UtcNow.ToString("O");
        await using var connection = await OpenAsync();
        using var transaction = connection.BeginTransaction();
        // 取锁后再次检查，已取消或被新输入替代的翻译不可写入学习库。
        if (stillCurrent?.Invoke() == false) return false;
        var inserted = await connection.ExecuteAsync(
            "INSERT OR IGNORE INTO StudyEvents VALUES (@eventId,@key,@now)", new { eventId, key, now }, transaction);
        if (inserted == 0) return false;
        var old = await connection.QuerySingleOrDefaultAsync<StudyEntry>(
            "SELECT * FROM StudyEntries WHERE EntryKey=@key", new { key }, transaction);
        var sources = old?.Sources.Select(s => StudyPrivacy.Source(s, rules)).ToList() ?? [];
        var sanitized = StudyPrivacy.Source(source, rules);
        if (!sources.Any(s => s.Url == sanitized.Url && s.Title == sanitized.Title && s.Kind == sanitized.Kind))
            sources.Add(sanitized);
        var entry = new StudyEntry
        {
            EntryKey = key, Language = language, TargetLanguage = target,
            Original = original, Translation = translation,
            Engine = StudyPrivacy.Restricted(data?.ServiceDisplayName, rules) ? "翻译服务" : data?.ServiceDisplayName ?? data?.ServiceID ?? "unknown",
            FirstSeenUtc = old?.FirstSeenUtc ?? now, LastSeenUtc = now,
            LookupCount = (old?.LookupCount ?? 0) + 1, SourcesJson = JsonSerializer.Serialize(sources),
            Revision = (old?.Revision ?? 0) + 1,
            SyncedRevision = old?.SyncedRevision ?? 0, LearningState = old?.LearningState ?? "new",
            CloudSyncAllowed = allowCloudSync && (old?.CloudSyncAllowed ?? true)
        };
        await connection.ExecuteAsync("""
            INSERT INTO StudyEntries (EntryKey,Language,TargetLanguage,Original,Translation,Engine,
                FirstSeenUtc,LastSeenUtc,LookupCount,SourcesJson,Revision,SyncedRevision,LearningState,CloudSyncAllowed)
            VALUES (@EntryKey,@Language,@TargetLanguage,@Original,@Translation,@Engine,
                @FirstSeenUtc,@LastSeenUtc,@LookupCount,@SourcesJson,@Revision,@SyncedRevision,@LearningState,@CloudSyncAllowed)
            ON CONFLICT(EntryKey) DO UPDATE SET Translation=excluded.Translation, Engine=excluded.Engine,
                LastSeenUtc=excluded.LastSeenUtc, LookupCount=excluded.LookupCount,
                SourcesJson=excluded.SourcesJson, Revision=excluded.Revision,
                CloudSyncAllowed=MIN(StudyEntries.CloudSyncAllowed,excluded.CloudSyncAllowed);
            """, entry, transaction);
        if (stillCurrent?.Invoke() == false) return false;
        transaction.Commit();
        return true;
    }

    public async Task<List<StudyEntry>> ReadAsync()
    {
        await using var connection = await OpenAsync();
        return StudyPrivacy.Clean(await connection.QueryAsync<StudyEntry>("SELECT * FROM StudyEntries ORDER BY LastSeenUtc DESC"), PrivacyRules).ToList();
    }

    public async Task<string> ExportAsync()
    {
        var entries = await ReadAsync();
        // 部分浏览器对中文本地文件名报找不到文件；入口用 ASCII，页面内容仍保留中文。
        var path = Path.Combine(DirectoryPath, "index.html");
        var temporary = path + ".tmp";
        await File.WriteAllTextAsync(temporary, StudyLibraryExport.Html(entries), Encoding.UTF8);
        File.Move(temporary, path, true);
        await File.WriteAllTextAsync(Path.Combine(DirectoryPath, "study-library.csv"), StudyLibraryExport.Csv(entries), new UTF8Encoding(true));
        return path;
    }
}

public sealed class StudyEntry
{
    public string EntryKey { get; set; } = "";
    public string Language { get; set; } = "";
    public string TargetLanguage { get; set; } = "";
    public string Original { get; set; } = "";
    public string Translation { get; set; } = "";
    public string Engine { get; set; } = "";
    public string FirstSeenUtc { get; set; } = "";
    public string LastSeenUtc { get; set; } = "";
    public int LookupCount { get; set; }
    public string SourcesJson { get; set; } = "[]";
    public int Revision { get; set; }
    public int SyncedRevision { get; set; }
    public string LearningState { get; set; } = "new";
    public bool CloudSyncAllowed { get; set; } = false;
    public IReadOnlyList<StudySource> Sources => JsonSerializer.Deserialize<List<StudySource>>(SourcesJson) ?? [];
}

public sealed record StudySource(string Kind, string Title, string Application, string? Url = null)
{
    public static StudySource Unknown(string kind = "manual") => new(kind, "未获取来源", "");

    public static string? SafeUrl(string? value)
    {
        if (!Uri.TryCreate(value?.Trim(), UriKind.Absolute, out var uri)) return null;
        // 来源只作为阅读链接，禁止从采集文本生成脚本、程序或带凭据的 URL。
        if (uri.Scheme is not ("https" or "http" or "file") || !string.IsNullOrEmpty(uri.UserInfo)) return null;
        if (uri.IsFile && (uri.IsUnc || !new[] { ".pdf", ".txt", ".md", ".html", ".htm" }.Contains(Path.GetExtension(uri.LocalPath).ToLowerInvariant()))) return null;
        return uri.AbsoluteUri;
    }

    public static string? FromClipboardHtml(string? html)
    {
        if (string.IsNullOrEmpty(html)) return null;
        var match = Regex.Match(html, @"(?:^|\r?\n)SourceURL:([^\r\n]+)", RegexOptions.IgnoreCase);
        return match.Success ? SafeUrl(match.Groups[1].Value) : null;
    }
}
