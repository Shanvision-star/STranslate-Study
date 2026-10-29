using STranslate.Core;
using STranslate.Plugin;

namespace STranslate.Tests;

public sealed class StudyLibraryTests : IDisposable
{
    private readonly string _root = System.IO.Path.Combine(System.IO.Path.GetTempPath(), "study-test-" + Guid.NewGuid().ToString("N"));
    private string _directory => System.IO.Path.Combine(_root, "StudyLibrary");

    public StudyLibraryTests()
    {
        var settings = System.IO.Path.Combine(_root, "Settings");
        System.IO.Directory.CreateDirectory(settings);
        var terms = new[] { "exampleorganization", "示例机构" };
        var rules = terms.Select(t => new StudyPrivacy.Rule(t.Length, Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(t))))).ToList();
        System.IO.File.WriteAllText(System.IO.Path.Combine(settings, "StudyPrivacy.json"), System.Text.Json.JsonSerializer.Serialize(new StudyPrivacy.Policy(rules)));
    }

    private static HistoryModel History(string text = "Visual hierarchy", bool success = true, string language = "English") => new()
    {
        SourceText = text, EffectiveSourceLang = language, EffectiveTargetLang = "ChineseSimplified",
        StudyLanguageVerified = true,
        Data = [new HistoryData { ServiceDisplayName = "Stub", TransResult = new TranslateResult { Text = "视觉层级", IsSuccess = success } }]
    };

    [Fact]
    public async Task DeduplicatesTextButPreservesOriginsAndLookupCount()
    {
        var library = new StudyLibrary(_directory);
        Assert.True(await library.SaveAsync(History(), new("selection", "Page A", "chrome", "https://example.org/a"), "event-1"));
        Assert.False(await library.SaveAsync(History(), new("selection", "Page A", "chrome"), "event-1"));
        Assert.True(await library.SaveAsync(History(" visual   hierarchy "), new("selection", "Page B", "msedge", "https://example.org/b"), "event-2"));
        var entry = Assert.Single(await new StudyLibrary(_directory).ReadAsync());
        Assert.Equal(2, entry.LookupCount);
        Assert.Equal(2, entry.Sources.Count);
        Assert.Equal(0, entry.SyncedRevision);
        Assert.Equal("new", entry.LearningState);
    }

    [Fact]
    public async Task FailedCancelledOrUnrequestedLanguageDoesNotPersist()
    {
        var library = new StudyLibrary(_directory);
        Assert.False(await library.SaveAsync(History(success: false), StudySource.Unknown(), "failed"));
        Assert.False(await library.SaveAsync(History(), StudySource.Unknown(), "cancelled", () => false));
        Assert.False(await library.SaveAsync(History(language: "ChineseSimplified"), StudySource.Unknown(), "chinese"));
        Assert.Empty(await library.ReadAsync());
    }

    [Theory]
    [InlineData("javascript:alert(1)")]
    [InlineData("https://user:password@example.org")]
    [InlineData("not-a-url")]
    [InlineData("file://server/share/run.exe")]
    [InlineData("file:///C:/run.exe")]
    public void UnsafeOrGuessedLinksAreRejected(string url) => Assert.Null(StudySource.SafeUrl(url));

    [Fact]
    public async Task CancellationBeforeCommitRollsBackTheEventAndEntry()
    {
        var calls = 0;
        var library = new StudyLibrary(_directory);
        Assert.False(await library.SaveAsync(History(), StudySource.Unknown("selection"), "cancel-at-commit", () => ++calls == 1));
        Assert.Empty(await library.ReadAsync());
        Assert.True(await library.SaveAsync(History(), StudySource.Unknown("selection"), "cancel-at-commit"));
    }

    [Fact]
    public async Task LanguageFallbackRemainsUnclassified()
    {
        var history = History("Me gusta aprender.");
        history.StudyLanguageVerified = false;
        var library = new StudyLibrary(_directory);
        Assert.True(await library.SaveAsync(history, StudySource.Unknown("selection"), "language-fallback"));
        Assert.Equal("und", Assert.Single(await library.ReadAsync()).Language);
    }

    [Fact]
    public void SourceUrlUsesClipboardHeaderNotBodyText()
    {
        Assert.Equal("https://example.org/article", StudySource.FromClipboardHtml("Version:1.0\r\nSourceURL:https://example.org/article\r\nStartHTML:100"));
        Assert.Null(StudySource.FromClipboardHtml("<p>SourceURL:https://example.org/guess</p>"));
    }

    [Fact]
    public async Task LocalOnlyPolicyCannotBeReopenedByAnotherLookup()
    {
        var library = new StudyLibrary(_directory);
        await library.SaveAsync(History(), StudySource.Unknown("selection"), "private-1", allowCloudSync: false);
        await library.SaveAsync(History(), StudySource.Unknown("selection"), "private-2", allowCloudSync: true);
        var entry = Assert.Single(await library.ReadAsync());
        Assert.False(entry.CloudSyncAllowed);
        Assert.Contains("仅本地保存", StudyLibraryExport.Html([entry]));
    }

    [Fact]
    public void ExportEscapesExternalTextAndProtectsCsv()
    {
        var entry = new StudyEntry { Language = "en", Original = "<script>alert(1)</script>", Translation = "=SUM(1,2)", SourcesJson = "[]" };
        var html = StudyLibraryExport.Html([entry]);
        Assert.DoesNotContain("<script>alert(1)</script>", html);
        Assert.Contains("&lt;script&gt;", html);
        Assert.Contains("size:A4", html);
        Assert.Contains("'=SUM", StudyLibraryExport.Csv([entry]));
    }

    [Fact]
    public async Task ExportPublishesAsciiEntryAndCsvWithChineseContent()
    {
        var library = new StudyLibrary(_directory);
        await library.SaveAsync(History(), StudySource.Unknown("selection"), "export-path");
        var path = await library.ExportAsync();
        Assert.Equal("index.html", System.IO.Path.GetFileName(path));
        var html = await System.IO.File.ReadAllTextAsync(path);
        Assert.Contains("study-library.csv", html);
        Assert.Contains("视觉层级", System.Net.WebUtility.HtmlDecode(html));
        Assert.True(System.IO.File.Exists(System.IO.Path.Combine(_directory, "study-library.csv")));
    }

    [Theory]
    [InlineData("示例机构的客户预算")]
    [InlineData("EXAMPLE-ORGANIZATION confidential plan")]
    [InlineData("示 例 机 构 project")]
    public async Task RestrictedContentNeverEntersStudyLibrary(string text)
    {
        var library = new StudyLibrary(_directory);
        Assert.False(await library.SaveAsync(History(text), StudySource.Unknown("selection"), "private"));
        Assert.Empty(await library.ReadAsync());
    }

    [Fact]
    public async Task SourceIdentityIsRemovedWithoutDiscardingGeneralVocabulary()
    {
        var library = new StudyLibrary(_directory);
        await library.SaveAsync(History("mechanism"), new("selection", "示例机构 - Chrome", "chrome", "https://example-organization.test/private?id=1"), "source-only");
        var entry = Assert.Single(await library.ReadAsync());
        Assert.DoesNotContain("示例机构", System.Text.Json.JsonSerializer.Serialize(entry.Sources));
        Assert.Null(entry.Sources[0].Url);
        Assert.Equal("mechanism", entry.Original);
    }

    [Fact]
    public void ExportAlsoProtectsImportedLegacyRecords()
    {
        var entry = new StudyEntry { Original="contact me at person@example.org", Translation="一般学习材料",
            SourcesJson="[{\"Kind\":\"selection\",\"Title\":\"示例机构\",\"Application\":\"chrome\",\"Url\":\"file:///C:/private.pdf\"}]" };
        var html = StudyLibraryExport.Html([entry]);
        Assert.DoesNotContain("person@example.org", html);
        Assert.DoesNotContain("示例机构", System.Net.WebUtility.HtmlDecode(html));
        Assert.DoesNotContain("private.pdf", html);
    }

    public void Dispose()
    {
        Microsoft.Data.Sqlite.SqliteConnection.ClearAllPools();
        if (System.IO.Directory.Exists(_root)) System.IO.Directory.Delete(_root, true);
    }
}
