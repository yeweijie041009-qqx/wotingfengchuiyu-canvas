' Silent launcher (ASCII only, avoids VBScript encoding issues)
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
base = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = base
q = Chr(34)
cmd = "py -3 " & q & base & "\start.py" & q
rc = sh.Run(cmd, 0, True)
If rc <> 0 Then
  cmd2 = "python " & q & base & "\start.py" & q
  rc2 = sh.Run(cmd2, 0, True)
  If rc2 <> 0 Then
    msg = "Start failed." & vbCrLf & vbCrLf & "Run this to see why:" & vbCrLf & "  cd " & base & vbCrLf & "  py -3 tools\doctor.py"
    MsgBox msg, 16, "AI Studio"
  End If
End If