' 双击启动：不显示黑窗口，后台拉起 ComfyUI + 画布，然后打开浏览器
' 如果已经在运行，只打开浏览器，不会重复启动
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
base = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = base

cmd = "py -3 """ & base & "\start.py"""
rc = sh.Run(cmd, 0, True)

If rc <> 0 Then
  cmd2 = "python """ & base & "\start.py"""
  rc2 = sh.Run(cmd2, 0, True)
  If rc2 <> 0 Then
    MsgBox "启动失败。" & vbCrLf & vbCrLf & _
           "请在命令行里手动运行，看具体报错：" & vbCrLf & _
           "  cd " & base & vbCrLf & _
           "  py -3 tools\doctor.py" & vbCrLf & vbCrLf & _
           "常见原因：没装 Python、ComfyUI 路径不对、8188 端口被占用。", _
           16, "卧听风吹雨 · 无限画布"
  End If
End If
