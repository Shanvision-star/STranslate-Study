using System.Net;
using System.Text;

namespace STranslate.Core;

/// <summary>输出可离线阅读与 A4 打印的复习页，采集不等于已经学会。</summary>
public static class StudyLibraryExport
{
    private static string E(string? value) => WebUtility.HtmlEncode(value ?? "");
    public static string Html(IReadOnlyList<StudyEntry> entries)
    {
        var body = new StringBuilder();
        foreach (var entry in StudyPrivacy.Clean(entries))
        {
            var date = DateTimeOffset.TryParse(entry.LastSeenUtc, out var time) ? time.ToLocalTime().ToString("yyyy-MM-dd HH:mm") : entry.LastSeenUtc;
            body.Append($"<article data-key='{E(entry.EntryKey)}' data-lang='{E(entry.Language)}' data-date='{E(date[..Math.Min(10, date.Length)])}'><label class='select-entry screen-only'><input class='pick' type='checkbox'> 选入打印</label><div class='meta'>{(entry.Language == "en" ? "ENGLISH" : entry.Language == "es" ? "ESPAÑOL" : "语种待确认")} · {E(date)} · 查询 {entry.LookupCount} 次 · {(!entry.CloudSyncAllowed ? "仅本地保存" : "已存本机 · 按计划整理词汇")}</div><h2>{E(entry.Original)}</h2><p class='translation'>{E(entry.Translation)}</p><div class='sources'>");
            foreach (var source in entry.Sources)
            {
                body.Append($"<div>{E(source.Title)} <span class='muted'>{E(source.Application)} / {E(source.Kind)}</span></div>");
                var safeUrl = StudySource.SafeUrl(source.Url);
                body.Append(safeUrl == null ? "<div class='muted'>原链接：未获取</div>" : $"<a href='{E(safeUrl)}' rel='noreferrer'>{E(safeUrl)}</a>");
            }
            body.Append($"</div><div class='practice'>□ 能解释意思　□ 能独立造句　□ 需要再练 <span class='muted'>译文：{E(entry.Engine)}</span></div><div class='line'></div></article>");
        }
        return """
            <!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
            <title>我的英语与西语学习库</title><style>
            *{box-sizing:border-box}body{font:16px/1.7 'Segoe UI','Microsoft YaHei',sans-serif;color:#22312b;background:#f5f4ee;margin:0}main{max-width:960px;margin:45px auto;padding:0 26px}h1{font-size:34px;font-weight:600;margin:0 0 12px}.intro{color:#56635c}header{border-bottom:2px solid #2d5944;padding-bottom:25px}nav{display:flex;gap:12px;flex-wrap:wrap;align-items:center;margin:20px 0}button,select,input{font:inherit;min-height:42px;padding:7px 12px;border:1px solid #9ca99c;border-radius:4px;background:white;color:#22312b}button{cursor:pointer}button:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid #b58a45}article{background:white;margin:20px 0;padding:24px;border:1px solid #d5d8d0;break-inside:avoid;page-break-inside:avoid;display:flow-root}h2{font-size:21px;line-height:1.5;font-weight:600;white-space:pre-wrap;overflow-wrap:anywhere}.translation{white-space:pre-wrap;overflow-wrap:anywhere}.meta{break-after:avoid;page-break-after:avoid}.meta,.muted{font-size:12px;color:#58645d}.sources{font-size:12px;border-top:1px solid #e0e2dd;padding-top:12px;overflow-wrap:anywhere}.sources a{color:#235b40;display:block}.practice{font-size:13px;margin-top:16px}.line{border-bottom:1px solid #ddd;height:24px}.select-entry{display:flex;justify-content:flex-end;gap:6px;align-items:center;margin-bottom:8px}.print-empty{display:none}.hidden{display:none!important}.hide-answer .translation{visibility:hidden;min-height:40px}footer{font-size:12px;color:#58645d;margin:24px 0}a{color:#235b40}label{font-size:14px}@page{size:A4;margin:15mm}@media print{body{background:white;font-size:11pt}main{margin:0;padding:0;max-width:none}nav,.screen-only{display:none}h1{font-size:21pt}h2{font-size:13pt}article{padding:4mm 0;margin:4mm 0;border:0;border-bottom:1px solid #bbb}.sources,.meta{font-size:8pt}.practice{font-size:9pt}header{padding-bottom:4mm}.sources a{color:black;text-decoration:none}.line{height:7mm}footer{font-size:8pt}body.printing-selection article{display:none!important}body.printing-selection article.print-selected{display:block!important}.print-empty{display:block}body.has-print-selection .print-empty{display:none}}
            </style><main><header><small>STranslate · PERSONAL STUDY LIBRARY</small><h1>我的英语与西语学习库</h1><p class="intro">来自日常阅读的词句。先理解，再尝试脱稿表达。查询次数只表示遇见次数，默认仍是待学习。</p></header>
            <nav><label>语种 <select id="lang"><option value="">全部</option><option value="en">英语</option><option value="es">西班牙语</option><option value="und">语种待确认</option></select></label><input id="query" type="search" placeholder="搜索原文、译文或来源" aria-label="搜索学习库"><label>日期 <input id="date" type="date"></label><label><input id="hide" type="checkbox"> 隐藏译文自测</label><button id="select-visible">选择当前结果</button><button id="clear-selection">清空选择</button><button id="print">汇总打印所选</button><a href="study-library.csv">导出全部 CSV</a></nav><p id="count" class="screen-only" aria-live="polite"></p><p class="print-empty">尚未选择词句。请取消打印，在学习库勾选需要的内容后点击“汇总打印所选”。</p>
            """ + body + """
            <footer>本机私密学习库，不公开发布。学习任务仅使用你自行绑定的助手。每两天只整理脱敏后的词汇用于对话，不发送原段落或来源信息。原链接仅在本机保留可核实的公开地址。重新从软件打开学习库可刷新记录。</footer></main>
            <script>
            const lang=document.getElementById('lang'),date=document.getElementById('date'),query=document.getElementById('query');
            const articles=[...document.querySelectorAll('article')],count=document.getElementById('count');
            const chosen=()=>articles.filter(a=>a.querySelector('.pick').checked);
            function updateCount(){count.textContent='当前显示 '+articles.filter(a=>!a.classList.contains('hidden')).length+' 条 · 已选择 '+chosen().length+' 条。勾选后汇总打印，可跨筛选条件选择。'}
            function filter(){articles.forEach(a=>{const show=(!lang.value||a.dataset.lang===lang.value)&&(!date.value||a.dataset.date===date.value)&&a.textContent.toLowerCase().includes(query.value.toLowerCase());a.classList.toggle('hidden',!show)});updateCount()}
            function preparePrint(){document.body.classList.add('printing-selection');document.body.classList.toggle('has-print-selection',chosen().length>0);articles.forEach(a=>a.classList.toggle('print-selected',a.querySelector('.pick').checked))}
            [lang,date,query].forEach(x=>x.addEventListener('input',filter));
            document.querySelectorAll('.pick').forEach(x=>x.addEventListener('change',updateCount));
            document.getElementById('select-visible').addEventListener('click',()=>{articles.filter(a=>!a.classList.contains('hidden')).forEach(a=>a.querySelector('.pick').checked=true);updateCount()});
            document.getElementById('clear-selection').addEventListener('click',()=>{articles.forEach(a=>a.querySelector('.pick').checked=false);updateCount()});
            document.getElementById('hide').addEventListener('change',e=>document.body.classList.toggle('hide-answer',e.target.checked));
            document.getElementById('print').addEventListener('click',()=>{if(!chosen().length){count.textContent='请先勾选需要汇总打印的词句。';return}preparePrint();window.print()});
            window.addEventListener('beforeprint',preparePrint);
            window.addEventListener('afterprint',()=>document.body.classList.remove('printing-selection','has-print-selection'));
            filter();
            </script></html>
            """;
    }

    public static string Csv(IReadOnlyList<StudyEntry> entries)
    {
        static string Cell(string? value)
        {
            value ??= "";
            if (value.TrimStart().StartsWith('=') || value.TrimStart().StartsWith('+') || value.TrimStart().StartsWith('-') || value.TrimStart().StartsWith('@')) value = "'" + value;
            return "\"" + value.Replace("\"", "\"\"") + "\"";
        }
        var result = new StringBuilder("语种,原文,译文,来源标题,原链接,首次查询UTC,最近查询UTC,查询次数,同步状态\r\n");
        foreach (var e in StudyPrivacy.Clean(entries))
            result.AppendLine(string.Join(',', new[] { e.Language, e.Original, e.Translation,
                string.Join(" | ", e.Sources.Select(s => s.Title)), string.Join(" | ", e.Sources.Select(s => StudySource.SafeUrl(s.Url)).Where(u => u != null)),
                e.FirstSeenUtc, e.LastSeenUtc, e.LookupCount.ToString(), !e.CloudSyncAllowed ? "仅本地保存" : "已存本机 · 按计划整理词汇" }.Select(Cell)));
        return result.ToString();
    }
}
