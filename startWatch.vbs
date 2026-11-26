' clinWatch 托盘启动器（无窗口）
' ------------------------------------------------------------
' 这里特意用 WshShell.Exec 而不是 WshShell.Run：
'   WshShell.Run 走 ShellExecute，本机在 ShellExecute 启动未签名 exe 时会弹出
'   "打开文件 - 安全警告 / 无法验证发布者"（发送方 = .venv\Scripts\pythonw.exe），
'   wscript 会一直卡在这个模态框上等用户点"运行"，表现为"双击 vbs 没任何反应、
'   托盘起不来、日志也没有新行"。
'   WshShell.Exec 走 CreateProcess，不经过 Shell，不会触发该提示。
' 失败时用 WMI Win32_Process.Create 兜底（同样走 CreateProcess），并弹窗告知。
Option Explicit

Dim fso, sh, base, py, script, cmd
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")

base = fso.GetParentFolderName(WScript.ScriptFullName)
py = base & "\.venv\Scripts\pythonw.exe"
script = base & "\tray.py"

If Not fso.FolderExists(base & "\.venv\Scripts") Then
    MsgBox "Cannot find project venv:" & vbCrLf & py & vbCrLf & "Please run 'uv sync' first.", 16, "clinWatch"
ElseIf Not fso.FileExists(py) Then
    MsgBox "Cannot find pythonw.exe:" & vbCrLf & py, 16, "clinWatch"
ElseIf Not fso.FileExists(script) Then
    MsgBox "Cannot find tray.py:" & vbCrLf & script, 16, "clinWatch"
Else
    cmd = Chr(34) & py & Chr(34) & " " & Chr(34) & script & Chr(34)
    On Error Resume Next
    sh.Exec cmd
    If Err.Number <> 0 Then
        Dim wmi
        Err.Clear
        On Error GoTo 0
        Set wmi = GetObject("winmgmts:\\.\root\cimv2")
        On Error Resume Next
        wmi.Get("Win32_Process").Create cmd, base, Null, 0
        If Err.Number <> 0 Then
            MsgBox "clinWatch 启动失败:" & vbCrLf & Err.Description, 16, "clinWatch"
        End If
    End If
    On Error GoTo 0
End If
