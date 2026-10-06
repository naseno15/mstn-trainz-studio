// MSTN Trainz Studio — Windows Explorer IPreviewHandler for Trainz meshes.
// Build: pack\shell\register.ps1  (Add-Type -OutputAssembly)
// Per-user COM registration; no admin required.
// No WinForms/WPF — prevhost Low IL often fails to CoCreate types that pull those in
// ("This file can't be previewed" with zero handler logs).

using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using Microsoft.Win32;

namespace MSTN.Shell
{
    [ComVisible(true)]
    [Guid("8F3E2A1B-6C4D-4E9F-B2A1-7D5E9C3F0A12")]
    [ClassInterface(ClassInterfaceType.None)]
    [ProgId("MSTN.TrainzMeshPreviewHandler")]
    public class MeshPreviewHandler :
        IInitializeWithFile,
        IPreviewHandler,
        IPreviewHandlerVisuals,
        IOleWindow,
        IObjectWithSite
    {
        private string _path;
        private IntPtr _hwndParent = IntPtr.Zero;
        private IntPtr _hwndHost = IntPtr.Zero;
        private RECT _rect;
        private Process _proc;
        private object _site;
        private uint _bgColorRef = 0x00201D1A; // COLORREF BBGGRR = #1A1D20
        private IntPtr _bgBrush = IntPtr.Zero;
        private WndProcDelegate _wndProc;
        private IntPtr _oldWndProc = IntPtr.Zero;

        public void Initialize(string pszFilePath, uint grfMode)
        {
            _path = pszFilePath;
            Log("Initialize {0}", pszFilePath);
        }

        public void SetWindow(IntPtr hwnd, ref RECT prc)
        {
            _hwndParent = hwnd;
            _rect = prc;
            Log("SetWindow hwnd={0} rect={1},{2},{3},{4}", hwnd.ToInt64(),
                prc.left, prc.top, prc.right, prc.bottom);
            EnsureHost();
            LayoutHost();
            MoveChildToRect();
        }

        public void SetRect(ref RECT prc)
        {
            _rect = prc;
            LayoutHost();
            MoveChildToRect();
        }

        public void DoPreview()
        {
            UnloadProcess();
            EnsureHost();
            LayoutHost();

            if (string.IsNullOrEmpty(_path) || _hwndParent == IntPtr.Zero || _hwndHost == IntPtr.Zero)
            {
                Log("DoPreview skip path={0} parent={1} host={2}",
                    _path, _hwndParent.ToInt64(), _hwndHost.ToInt64());
                return;
            }

            string launch = ReadLaunchCommand();
            if (string.IsNullOrEmpty(launch))
            {
                Log("DoPreview: PreviewLaunch missing");
                return;
            }

            int w = Math.Max(1, _rect.right - _rect.left);
            int h = Math.Max(1, _rect.bottom - _rect.top);
            string args = string.Format(
                "--explorer-preview --parent-hwnd={0} --rect={1},{2},{3},{4} \"{5}\"",
                _hwndHost.ToInt64(),
                0, 0, w, h,
                _path.Replace("\"", ""));

            var psi = new ProcessStartInfo();
            ParseLaunch(launch, args, psi);
            psi.UseShellExecute = false;
            psi.CreateNoWindow = false;
            string cwd = ReadCwd();
            if (string.IsNullOrEmpty(cwd) || !Directory.Exists(cwd))
                cwd = Path.GetDirectoryName(psi.FileName) ?? "";
            psi.WorkingDirectory = cwd;

            Log("DoPreview exe={0} args={1} cwd={2}", psi.FileName, psi.Arguments, cwd);
            try
            {
                _proc = Process.Start(psi);
                Log("DoPreview pid={0}", _proc != null ? _proc.Id : -1);
            }
            catch (Exception ex)
            {
                Log("DoPreview FAIL {0}", ex);
                _proc = null;
            }
        }

        public void Unload()
        {
            UnloadProcess();
            DestroyHost();
            _path = null;
        }

        public void SetFocus()
        {
            if (_hwndHost != IntPtr.Zero)
                NativeSetFocus(_hwndHost);
        }

        public void QueryFocus(out IntPtr phwnd)
        {
            phwnd = _hwndHost != IntPtr.Zero ? _hwndHost : _hwndParent;
        }

        public uint TranslateAccelerator(ref MSG pmsg)
        {
            return 1; // S_FALSE
        }

        public void GetWindow(out IntPtr phwnd)
        {
            phwnd = _hwndHost != IntPtr.Zero ? _hwndHost : _hwndParent;
        }

        public void ContextSensitiveHelp(bool fEnterMode) { }

        public void SetSite(object pUnkSite)
        {
            _site = pUnkSite;
        }

        public void GetSite(ref Guid riid, out object ppvSite)
        {
            ppvSite = _site;
        }

        public void SetBackgroundColor(uint color)
        {
            _bgColorRef = color;
            RecreateBrush();
            if (_hwndHost != IntPtr.Zero)
                InvalidateRect(_hwndHost, IntPtr.Zero, true);
        }

        public void SetFont(IntPtr plf) { }

        public void SetTextColor(uint color) { }

        private void EnsureHost()
        {
            if (_hwndParent == IntPtr.Zero) return;
            if (_hwndHost != IntPtr.Zero && IsWindow(_hwndHost)) return;

            DestroyHost();
            RecreateBrush();

            int w = Math.Max(1, _rect.right - _rect.left);
            int h = Math.Max(1, _rect.bottom - _rect.top);
            _hwndHost = CreateWindowEx(
                0,
                "Static",
                "",
                WS_CHILD | WS_VISIBLE | WS_CLIPSIBLINGS | WS_CLIPCHILDREN,
                _rect.left, _rect.top, w, h,
                _hwndParent,
                IntPtr.Zero,
                GetModuleHandle(null),
                IntPtr.Zero);

            if (_hwndHost == IntPtr.Zero)
            {
                Log("EnsureHost CreateWindowEx FAILED err={0}", Marshal.GetLastWin32Error());
                return;
            }

            // Subclass so WM_ERASEBKGND paints dark (Static defaults to white).
            _wndProc = HostWndProc;
            _oldWndProc = SetWindowLongPtr(_hwndHost, GWL_WNDPROC,
                Marshal.GetFunctionPointerForDelegate(_wndProc));
            InvalidateRect(_hwndHost, IntPtr.Zero, true);
            Log("EnsureHost host={0} parent={1}", _hwndHost.ToInt64(), _hwndParent.ToInt64());
        }

        private IntPtr HostWndProc(IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam)
        {
            if (msg == WM_ERASEBKGND)
            {
                IntPtr hdc = wParam;
                RECT rc;
                GetClientRect(hWnd, out rc);
                IntPtr br = _bgBrush != IntPtr.Zero
                    ? _bgBrush
                    : GetStockObject(BLACK_BRUSH);
                FillRect(hdc, ref rc, br);
                return (IntPtr)1;
            }
            if (msg == WM_PAINT)
            {
                PAINTSTRUCT ps;
                IntPtr hdc = BeginPaint(hWnd, out ps);
                IntPtr br = _bgBrush != IntPtr.Zero
                    ? _bgBrush
                    : GetStockObject(BLACK_BRUSH);
                FillRect(hdc, ref ps.rcPaint, br);
                EndPaint(hWnd, ref ps);
                return IntPtr.Zero;
            }
            return CallWindowProc(_oldWndProc, hWnd, msg, wParam, lParam);
        }

        private void LayoutHost()
        {
            if (_hwndHost == IntPtr.Zero || !IsWindow(_hwndHost)) return;
            int w = Math.Max(1, _rect.right - _rect.left);
            int h = Math.Max(1, _rect.bottom - _rect.top);
            MoveWindow(_hwndHost, _rect.left, _rect.top, w, h, true);
        }

        private void DestroyHost()
        {
            if (_hwndHost != IntPtr.Zero && IsWindow(_hwndHost))
            {
                if (_oldWndProc != IntPtr.Zero)
                {
                    SetWindowLongPtr(_hwndHost, GWL_WNDPROC, _oldWndProc);
                    _oldWndProc = IntPtr.Zero;
                }
                DestroyWindow(_hwndHost);
            }
            _hwndHost = IntPtr.Zero;
            _wndProc = null;
            if (_bgBrush != IntPtr.Zero)
            {
                DeleteObject(_bgBrush);
                _bgBrush = IntPtr.Zero;
            }
        }

        private void RecreateBrush()
        {
            if (_bgBrush != IntPtr.Zero)
            {
                DeleteObject(_bgBrush);
                _bgBrush = IntPtr.Zero;
            }
            _bgBrush = CreateSolidBrush(_bgColorRef);
        }

        private void UnloadProcess()
        {
            if (_proc == null) return;
            try
            {
                if (!_proc.HasExited)
                {
                    _proc.Kill();
                    _proc.WaitForExit(1500);
                }
            }
            catch { }
            try { _proc.Dispose(); } catch { }
            _proc = null;
        }

        private void MoveChildToRect()
        {
            if (_hwndHost == IntPtr.Zero) return;
            int w = Math.Max(1, _rect.right - _rect.left);
            int h = Math.Max(1, _rect.bottom - _rect.top);
            string title = "__MSTN_MESH_PREVIEW__" + _hwndHost.ToInt64().ToString();
            IntPtr child = FindWindowEx(_hwndHost, IntPtr.Zero, null, title);
            if (child != IntPtr.Zero)
                MoveWindow(child, 0, 0, w, h, true);
        }

        private static string ReadLaunchCommand()
        {
            try
            {
                using (var k = Registry.CurrentUser.OpenSubKey(
                    @"Software\MSTN\TrainzStudio", false))
                {
                    if (k == null) return null;
                    return k.GetValue("PreviewLaunch") as string;
                }
            }
            catch { return null; }
        }

        private static string ReadCwd()
        {
            try
            {
                using (var k = Registry.CurrentUser.OpenSubKey(
                    @"Software\MSTN\TrainzStudio", false))
                {
                    if (k == null) return null;
                    return k.GetValue("PreviewCwd") as string;
                }
            }
            catch { return null; }
        }

        private static void Log(string fmt, params object[] args)
        {
            try
            {
                string line = DateTime.Now.ToString("s") + " " +
                    string.Format(fmt, args) + Environment.NewLine;
                File.AppendAllText(
                    Path.Combine(Path.GetTempPath(), "mstn_mesh_preview_handler.log"),
                    line);
                string install = null;
                using (var k = Registry.CurrentUser.OpenSubKey(
                    @"Software\MSTN\TrainzStudio", false))
                {
                    if (k != null) install = k.GetValue("InstallRoot") as string;
                }
                if (!string.IsNullOrEmpty(install))
                {
                    string dir = Path.Combine(install, "pack", "shell", "bin");
                    Directory.CreateDirectory(dir);
                    File.AppendAllText(Path.Combine(dir, "preview_handler.log"), line);
                }
            }
            catch { }
        }

        private static void ParseLaunch(string launch, string extraArgs, ProcessStartInfo psi)
        {
            launch = launch.Trim();
            if (launch.StartsWith("\""))
            {
                int end = launch.IndexOf('"', 1);
                if (end > 1)
                {
                    psi.FileName = launch.Substring(1, end - 1);
                    string rest = launch.Substring(end + 1).Trim();
                    psi.Arguments = string.IsNullOrEmpty(rest)
                        ? extraArgs
                        : rest + " " + extraArgs;
                    return;
                }
            }
            int sp = launch.IndexOf(' ');
            if (sp < 0)
            {
                psi.FileName = launch;
                psi.Arguments = extraArgs;
            }
            else
            {
                psi.FileName = launch.Substring(0, sp);
                psi.Arguments = launch.Substring(sp + 1).Trim() + " " + extraArgs;
            }
        }

        private const int WS_CHILD = 0x40000000;
        private const int WS_VISIBLE = 0x10000000;
        private const int WS_CLIPSIBLINGS = 0x04000000;
        private const int WS_CLIPCHILDREN = 0x02000000;
        private const int GWL_WNDPROC = -4;
        private const uint WM_ERASEBKGND = 0x0014;
        private const uint WM_PAINT = 0x000F;
        private const int BLACK_BRUSH = 4;

        private delegate IntPtr WndProcDelegate(
            IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam);

        [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern IntPtr CreateWindowEx(
            int dwExStyle, string lpClassName, string lpWindowName,
            int dwStyle, int x, int y, int nWidth, int nHeight,
            IntPtr hWndParent, IntPtr hMenu, IntPtr hInstance, IntPtr lpParam);

        [DllImport("user32.dll")]
        private static extern bool DestroyWindow(IntPtr hWnd);

        [DllImport("user32.dll")]
        private static extern bool IsWindow(IntPtr hWnd);

        [DllImport("user32.dll")]
        private static extern bool MoveWindow(
            IntPtr hWnd, int X, int Y, int nWidth, int nHeight, bool bRepaint);

        [DllImport("user32.dll", CharSet = CharSet.Unicode)]
        private static extern IntPtr FindWindowEx(
            IntPtr hwndParent, IntPtr hwndChildAfter, string lpszClass, string lpszWindow);

        [DllImport("user32.dll", EntryPoint = "SetFocus")]
        private static extern IntPtr NativeSetFocus(IntPtr hWnd);

        [DllImport("user32.dll")]
        private static extern bool InvalidateRect(IntPtr hWnd, IntPtr lpRect, bool bErase);

        [DllImport("user32.dll")]
        private static extern bool GetClientRect(IntPtr hWnd, out RECT lpRect);

        [DllImport("user32.dll")]
        private static extern IntPtr BeginPaint(IntPtr hWnd, out PAINTSTRUCT lpPaint);

        [DllImport("user32.dll")]
        private static extern bool EndPaint(IntPtr hWnd, ref PAINTSTRUCT lpPaint);

        [DllImport("user32.dll")]
        private static extern int FillRect(IntPtr hDC, ref RECT lprc, IntPtr hbr);

        [DllImport("gdi32.dll")]
        private static extern IntPtr CreateSolidBrush(uint color);

        [DllImport("gdi32.dll")]
        private static extern bool DeleteObject(IntPtr hObject);

        [DllImport("gdi32.dll")]
        private static extern IntPtr GetStockObject(int fnObject);

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
        private static extern IntPtr GetModuleHandle(string lpModuleName);

        [DllImport("user32.dll")]
        private static extern IntPtr CallWindowProc(
            IntPtr lpPrevWndFunc, IntPtr hWnd, uint Msg, IntPtr wParam, IntPtr lParam);

        private static IntPtr SetWindowLongPtr(IntPtr hWnd, int nIndex, IntPtr dwNewLong)
        {
            if (IntPtr.Size == 8)
                return SetWindowLongPtr64(hWnd, nIndex, dwNewLong);
            return new IntPtr(SetWindowLong32(hWnd, nIndex, dwNewLong.ToInt32()));
        }

        [DllImport("user32.dll", EntryPoint = "SetWindowLong")]
        private static extern int SetWindowLong32(IntPtr hWnd, int nIndex, int dwNewLong);

        [DllImport("user32.dll", EntryPoint = "SetWindowLongPtr")]
        private static extern IntPtr SetWindowLongPtr64(IntPtr hWnd, int nIndex, IntPtr dwNewLong);

        [StructLayout(LayoutKind.Sequential)]
        private struct PAINTSTRUCT
        {
            public IntPtr hdc;
            public int fErase;
            public RECT rcPaint;
            public int fRestore;
            public int fIncUpdate;
            [MarshalAs(UnmanagedType.ByValArray, SizeConst = 32)]
            public byte[] rgbReserved;
        }
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct RECT
    {
        public int left, top, right, bottom;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct MSG
    {
        public IntPtr hwnd;
        public uint message;
        public IntPtr wParam;
        public IntPtr lParam;
        public uint time;
        public int pt_x, pt_y;
    }

    [ComImport, InterfaceType(ComInterfaceType.InterfaceIsIUnknown),
     Guid("b824b49d-22ac-4161-ac8a-9916e8fa3f7f")]
    public interface IInitializeWithFile
    {
        void Initialize([MarshalAs(UnmanagedType.LPWStr)] string pszFilePath, uint grfMode);
    }

    [ComImport, InterfaceType(ComInterfaceType.InterfaceIsIUnknown),
     Guid("8895b1c6-b41f-4c1c-a562-0d564250836f")]
    public interface IPreviewHandler
    {
        void SetWindow(IntPtr hwnd, ref RECT prc);
        void SetRect(ref RECT prc);
        void DoPreview();
        void Unload();
        void SetFocus();
        void QueryFocus(out IntPtr phwnd);
        [PreserveSig] uint TranslateAccelerator(ref MSG pmsg);
    }

    [ComImport, InterfaceType(ComInterfaceType.InterfaceIsIUnknown),
     Guid("196bf9a5-b345-4f30-b1c1-d316558c9ddf")]
    public interface IPreviewHandlerVisuals
    {
        void SetBackgroundColor(uint color);
        void SetFont(IntPtr plf);
        void SetTextColor(uint color);
    }

    [ComImport, InterfaceType(ComInterfaceType.InterfaceIsIUnknown),
     Guid("00000114-0000-0000-C000-000000000046")]
    public interface IOleWindow
    {
        void GetWindow(out IntPtr phwnd);
        void ContextSensitiveHelp([MarshalAs(UnmanagedType.Bool)] bool fEnterMode);
    }

    [ComImport, InterfaceType(ComInterfaceType.InterfaceIsIUnknown),
     Guid("FC4801A3-2BA9-11CF-A229-00AA003D7352")]
    public interface IObjectWithSite
    {
        void SetSite([MarshalAs(UnmanagedType.IUnknown)] object pUnkSite);
        void GetSite(ref Guid riid, [MarshalAs(UnmanagedType.IUnknown)] out object ppvSite);
    }
}
