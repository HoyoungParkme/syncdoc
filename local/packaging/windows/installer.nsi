; 싱크독_로컬 설치 파일 — NSIS 3 (SYNC-INFRA-001 9.5 · SYNC-DOM-004 1장 packaging, 카드 L4)
; cargo xtask package windows가 STAGE(실행 파일·postgresql·mingit·NOTICE·아이콘)를 모은 뒤
; makensis -DVERSION=… -DSTAGE=… -DOUTFILE=… installer.nsi 로 부른다.
; 사용자 범위(관리자 권한 없이) · 시작 메뉴 · 바탕화면(기본 켬) · 자동 시작(기본 끔, 사용자 결정 2026-10-08)
; 제거는 프로그램·바로 가기·자동 시작만 — 데이터 자리(%LOCALAPPDATA%\SyncDoc Local)는 남긴다.

Unicode true
!include "MUI2.nsh"

!define APPKEY "SyncDoc Local"
!define APPNAME "싱크독_로컬"
!define EXE "syncdoc-local.exe"
!define UNINST "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPKEY}"
!define RUNKEY "Software\Microsoft\Windows\CurrentVersion\Run"

Name "${APPNAME} ${VERSION}"
OutFile "${OUTFILE}"
InstallDir "$LOCALAPPDATA\Programs\SyncDoc Local"
InstallDirRegKey HKCU "Software\${APPKEY}" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma
BrandingText "${APPNAME} ${VERSION}"

!define MUI_ICON "${STAGE}\icon.ico"
!define MUI_UNICON "${STAGE}\icon.ico"
!define MUI_COMPONENTSPAGE_NODESC
!define MUI_FINISHPAGE_RUN "$INSTDIR\${EXE}"
!define MUI_FINISHPAGE_RUN_TEXT "${APPNAME} 실행"

!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "Korean"

; 켜져 있으면 실행 파일이 잠겨 있다 — 트레이에서 끝낸 뒤 다시
!macro CHECK_NOT_RUNNING
  IfFileExists "$INSTDIR\${EXE}" 0 check_done
  check_retry:
  ClearErrors
  FileOpen $0 "$INSTDIR\${EXE}" a
  IfErrors check_locked
  FileClose $0
  Goto check_done
  check_locked:
  MessageBox MB_RETRYCANCEL|MB_ICONEXCLAMATION "${APPNAME}이 켜져 있습니다. 트레이에서 「끝내기」를 누른 뒤 다시 시도하세요." /SD IDCANCEL IDRETRY check_retry
  Abort
  check_done:
!macroend

Section "${APPNAME} (필수)" SecMain
  SectionIn RO
  !insertmacro CHECK_NOT_RUNNING
  SetOutPath "$INSTDIR"
  File "${STAGE}\${EXE}"
  File "${STAGE}\NOTICE.txt"
  File "${STAGE}\icon.ico"
  File /r "${STAGE}\postgresql"
  File /r "${STAGE}\mingit"
  WriteUninstaller "$INSTDIR\uninstall.exe"
  CreateShortcut "$SMPROGRAMS\${APPNAME}.lnk" "$INSTDIR\${EXE}" "" "$INSTDIR\icon.ico"
  WriteRegStr HKCU "Software\${APPKEY}" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "${UNINST}" "DisplayName" "${APPNAME}"
  WriteRegStr HKCU "${UNINST}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${UNINST}" "DisplayIcon" "$INSTDIR\icon.ico"
  WriteRegStr HKCU "${UNINST}" "Publisher" "SyncDoc"
  WriteRegStr HKCU "${UNINST}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNINST}" "UninstallString" '"$INSTDIR\uninstall.exe"'
  WriteRegStr HKCU "${UNINST}" "QuietUninstallString" '"$INSTDIR\uninstall.exe" /S'
  WriteRegDWORD HKCU "${UNINST}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINST}" "NoRepair" 1
SectionEnd

Section "바탕화면 바로 가기" SecDesktop
  CreateShortcut "$DESKTOP\${APPNAME}.lnk" "$INSTDIR\${EXE}" "" "$INSTDIR\icon.ico"
SectionEnd

Section /o "로그인 때 자동 시작 (트레이로만)" SecAutostart
  WriteRegStr HKCU "${RUNKEY}" "${APPKEY}" '"$INSTDIR\${EXE}" --autostart'
SectionEnd

Section "Uninstall"
  !insertmacro CHECK_NOT_RUNNING
  Delete "$SMPROGRAMS\${APPNAME}.lnk"
  Delete "$DESKTOP\${APPNAME}.lnk"
  DeleteRegValue HKCU "${RUNKEY}" "${APPKEY}"
  DeleteRegKey HKCU "${UNINST}"
  DeleteRegKey HKCU "Software\${APPKEY}"
  Delete "$INSTDIR\${EXE}"
  Delete "$INSTDIR\NOTICE.txt"
  Delete "$INSTDIR\icon.ico"
  RMDir /r "$INSTDIR\postgresql"
  RMDir /r "$INSTDIR\mingit"
  Delete "$INSTDIR\uninstall.exe"
  RMDir "$INSTDIR"
SectionEnd
