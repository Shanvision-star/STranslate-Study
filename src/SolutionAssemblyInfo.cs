using System.Reflection;
using System.Runtime.InteropServices;
using System.Runtime.CompilerServices;

#if DEBUG

[assembly: AssemblyConfiguration("Debug")]
[assembly: AssemblyDescription("Debug build, https://github.com/STranslate/STranslate")]
#else
[assembly: AssemblyConfiguration("Release")]
[assembly: AssemblyDescription("Release build, https://github.com/STranslate/STranslate")]
#endif

[assembly: AssemblyCompany("STranslate")]
[assembly: AssemblyProduct("STranslate")]
[assembly: AssemblyCopyright("The MIT License (MIT)")]
[assembly: AssemblyTrademark("")]
[assembly: AssemblyCulture("")]
[assembly: ComVisible(false)]
[assembly: AssemblyVersion("2.0.10.0")]
[assembly: AssemblyFileVersion("2.0.10.0")]
[assembly: AssemblyInformationalVersion("0.1.0-study")]
[assembly: InternalsVisibleTo("STranslate.Tests")]
