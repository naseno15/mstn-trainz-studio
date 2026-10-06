' Silent launcher — no console. Supports drag-drop of multiple args.
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
here = fso.GetParentFolderName(WScript.ScriptFullName)
venvPyw = here & "\.venv\Scripts\pythonw.exe"
venvPy = here & "\.venv\Scripts\python.exe"
repo = fso.GetParentFolderName(here)

If Not fso.FileExists(venvPyw) Then
  ' First run: create venv + bytecode (brief hidden cmd)
  sh.Run "cmd /c cd /d """ & here & """ && python -m venv .venv && .venv\Scripts\pip.exe install -r requirements.txt && .venv\Scripts\python.exe -m compileall -q .", 0, True
End If

args = "-m trainz_studio"
Dim i
For i = 0 To WScript.Arguments.Count - 1
  args = args & " """ & WScript.Arguments(i) & """"
Next

sh.CurrentDirectory = repo
sh.Run """" & venvPyw & """ " & args, 0, False
