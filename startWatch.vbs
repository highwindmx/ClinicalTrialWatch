Set fso = CreateObject("Scripting.FileSystemObject")
Set ws = CreateObject("WScript.Shell")
base = fso.GetParentFolderName(WScript.ScriptFullName)
py = base & "\.venv\Scripts\pythonw.exe"
script = base & "\tray.py"
If fso.FolderExists(base & "\.venv\Scripts") Then
    ws.Run Chr(34) & py & Chr(34) & " " & Chr(34) & script & Chr(34), 0, False
Else
    MsgBox "Cannot find project venv:" & vbCrLf & py & vbCrLf & "Please run 'uv sync' first.", 16, "clinWatch"
End If
