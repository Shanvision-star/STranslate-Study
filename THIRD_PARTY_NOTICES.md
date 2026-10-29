# Third-party notices / 第三方声明

STranslate Study is an independent derivative of **STranslate v2.0.10**, by **zggsong and the STranslate contributors**. The original MIT license and copyright notice are preserved verbatim in [LICENSE](LICENSE). Study-specific source changes use MIT. This statement does not relicense third-party libraries, models, assets, services or runtimes.

## Visible attribution and use limitations

**iNKORE.UI.WPF.Modern**, by **iNKORE Studios and all iNKORE.UI.WPF.Modern contributors**: [project repository](https://github.com/iNKORE-NET/UI.WPF.Modern). Version 0.10.2.1 is referenced by upstream. Its package license URL is historical; the adjacent upstream v0.10.2 release license was inspected and is preserved in [licenses/iNKORE-Modern.txt](licenses/iNKORE-Modern.txt).

This component has a **custom license**, not MIT. It requires clear attribution and fully open-source distribution; incorporating it into commercial products requires explicit written permission. It prohibits selling/renting/leasing/sublicensing the component. This application is distributed free of charge with its source, without claiming endorsement. Do not infer unrestricted commercial rights from this repository's MIT code license. Company deployment for commercial purposes requires a review of the applicable component terms and any necessary permission.

**iNKORE.UI.WPF 1.2.8**, by Yoojun Zhou / iNKORE Studios: LGPL-2.1-or-later. It remains a separate replaceable DLL; this build does not merge it through Costura/Fody. We do not restrict modification, replacement, or reverse engineering for debugging modifications to this library. The [LGPL text](licenses/iNKORE-WPF-LGPL.txt) and [complete v1.2.8 source archive](licenses/iNKORE.UI.WPF-1.2.8-source.zip) accompany the distribution. Source: [tag v1.2.8](https://github.com/iNKORE-NET/UI.WPF/tree/v1.2.8), commit `5175f72906ce6770e98a33f91740c8120c6eda21`, archive SHA256 `6b3b5fd51cb9de6212a661d375cfe568fcb9d13b12b4a8ebdf3da3675f442e3b`. No modifications to that library are made here.

## OCR and runtime components

| Component | Version / source | License and notices |
| --- | --- | --- |
| Tesseract .NET wrapper | Charles Weld, NuGet Tesseract 5.2.0 | Apache-2.0, [wrapper license](licenses/Tesseract-wrapper.txt) |
| InteropDotNet (used inside wrapper) | Andrey Akinshin | [Original MIT notice](licenses/InteropDotNet.txt), [source](https://github.com/AndreyAkinshin/InteropDotNet) |
| Tesseract OCR native engine | Native tesseract50.dll supplied by Tesseract 5.2.0 NuGet | Apache-2.0, [engine license](licenses/Tesseract-engine.txt), [upstream](https://github.com/tesseract-ocr/tesseract) |
| Leptonica native engine | 1.82.0, supplied by Tesseract NuGet | BSD-style, copyright Dan Bloomberg; [full notice](licenses/Leptonica.txt), [source](https://github.com/DanBloomberg/leptonica/tree/1.82.0) |
| OCR language data | tessdata_fast commit `87416418657359cb625c412a48b6e1d6d41c29bd`, eng/spa/chi_sim | Apache-2.0, [model license](licenses/Tesseract-models.txt), [source](https://github.com/tesseract-ocr/tessdata_fast/tree/87416418657359cb625c412a48b6e1d6d41c29bd) |
| CPython | Official 3.14.10 Windows x64 embeddable distribution | PSF and bundled component terms; unmodified `python/LICENSE.txt` in binary package. Only its search path configuration is extended for StudyTools. [source and license](https://www.python.org/downloads/release/python-31410/) |
| .NET / Windows Desktop runtime | SDK self-contained publish output | Microsoft/.NET Foundation notices included in the published runtime and collected NuGet files. [runtime license](https://github.com/dotnet/runtime/blob/main/LICENSE.TXT) |
| XamlFlair.WPF | 1.2.13 | [Original MIT notice](licenses/XamlFlair.txt) |

All other NuGet dependencies, authors, declared licenses and bundled license files are listed in [licenses/nuget/DEPENDENCIES.md](licenses/nuget/DEPENDENCIES.md). The manifest conservatively includes build-time references; listing does not mean every package is loaded at runtime. License texts shipped inside packages are retained. Supplemental standard licenses and source notices are under `licenses/`.

Microsoft and OpenAI names/icons in the upstream service plugins identify their respective services; this project is not endorsed by those providers. Their online terms, authentication and availability are separate from source-code licenses. The public binary does not bundle WeChat OCR or the Microsoft Visual C++ redistributable installer. The repository retains original upstream plugin source/history for attribution; it is not a promise that every optional third-party binary may be redistributed.

When redistributing this application, include this file, LICENSE and the licenses directory. Review changed dependencies before publishing a new version. A README attribution alone does not replace the full license obligations.
