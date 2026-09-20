' Double-click to start CyberMirror (opens console window)
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
sh.Run "cmd /c """ & sh.CurrentDirectory & "\CyberMirror.bat""", 1, False
