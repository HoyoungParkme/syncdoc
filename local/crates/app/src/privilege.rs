//! 윈도 관리자 권한 내려놓기 (SYNC-MS-012#privilege.drop_admin · SYNC-INFRA-001 9.4, 카드 L4).
//! PostgreSQL은 관리자 권한으로 돌지 않는다 — UAC를 끈 PC·「관리자 권한으로 실행」·GitHub 윈도 러너에서는
//! `postgres --single`이 거부된다. PostgreSQL이 `initdb`·`pg_ctl`에서 하는 것(`src/common/restricted_token.c`)처럼
//! 관리자·Power Users 그룹을 거부 전용으로 바꾼 토큰으로 자신을 다시 켜고, 끝나기를 기다려 그 끝 코드를 돌려준다.
//!
//! 이 저장소에서 `unsafe`를 쓰는 곳은 이 모듈의 Win32 호출뿐이다(작업 공간 lint는 deny, SYNC-DOM-004 4.1).

/// SYNC-MS-012#privilege.drop_admin
pub fn drop_admin() -> Option<u32> {
    #[cfg(windows)]
    {
        win::drop_admin()
    }
    #[cfg(not(windows))]
    {
        None
    }
}

#[cfg(windows)]
#[allow(unsafe_code)]
mod win {
    use std::io;
    use std::mem::size_of;
    use std::ptr::{null, null_mut};

    use windows_sys::Win32::Foundation::{
        CloseHandle, GENERIC_ALL, HANDLE, HANDLE_FLAG_INHERIT, SetHandleInformation, WAIT_OBJECT_0,
    };
    use windows_sys::Win32::Security::{
        ACCESS_ALLOWED_ACE, ACE_HEADER, ACL, ACL_REVISION, ACL_SIZE_INFORMATION,
        AclSizeInformation, AddAccessAllowedAceEx, AddAce, AllocateAndInitializeSid,
        CheckTokenMembership, CreateRestrictedToken, DISABLE_MAX_PRIVILEGE, FreeSid, GetAce,
        GetAclInformation, GetLengthSid, GetTokenInformation, InitializeAcl, OBJECT_INHERIT_ACE,
        PSID, SECURITY_NT_AUTHORITY, SID_AND_ATTRIBUTES, SetTokenInformation, TOKEN_ALL_ACCESS,
        TOKEN_DEFAULT_DACL, TOKEN_INFORMATION_CLASS, TOKEN_USER, TokenDefaultDacl, TokenUser,
    };
    use windows_sys::Win32::System::Console::{
        GetStdHandle, STD_ERROR_HANDLE, STD_INPUT_HANDLE, STD_OUTPUT_HANDLE, SetConsoleCtrlHandler,
    };
    use windows_sys::Win32::System::Environment::GetCommandLineW;
    use windows_sys::Win32::System::SystemServices::{
        DOMAIN_ALIAS_RID_ADMINS, DOMAIN_ALIAS_RID_POWER_USERS, SECURITY_BUILTIN_DOMAIN_RID,
    };
    use windows_sys::Win32::System::Threading::{
        CreateProcessAsUserW, GetCurrentProcess, GetExitCodeProcess, INFINITE, OpenProcessToken,
        PROCESS_INFORMATION, STARTF_USESTDHANDLES, STARTUPINFOW, WaitForSingleObject,
    };
    use windows_sys::core::BOOL;

    /// 다시 켠 자식의 표시 — 두 번 다시 켜지 않는다
    const RESTRICTED_ENV: &str = "SYNCDOC_RESTRICTED";

    pub fn drop_admin() -> Option<u32> {
        if std::env::var_os(RESTRICTED_ENV).is_some() {
            return None;
        }
        match is_admin() {
            Ok(false) => return None,
            Ok(true) => {}
            Err(e) => {
                eprintln!("관리자 권한인지 보지 못했다 — {e}");
                return None;
            }
        }
        match rerun_restricted() {
            Ok(code) => Some(code),
            Err(e) => {
                eprintln!("관리자 권한을 내려놓지 못했다 — 그대로 켠다: {e}");
                None
            }
        }
    }

    /// BUILTIN 그룹 SID — 놓이면 FreeSid
    struct Sid(PSID);

    impl Sid {
        fn builtin(rid: i32) -> io::Result<Sid> {
            let mut sid: PSID = null_mut();
            // SAFETY: 권한 값은 상수, sid는 이 함수의 지역 변수 — 성공하면 Drop이 FreeSid로 놓는다
            let ok = unsafe {
                AllocateAndInitializeSid(
                    &SECURITY_NT_AUTHORITY,
                    2,
                    SECURITY_BUILTIN_DOMAIN_RID as u32,
                    rid as u32,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    &mut sid,
                )
            };
            if ok == 0 {
                return Err(io::Error::last_os_error());
            }
            Ok(Sid(sid))
        }
    }

    impl Drop for Sid {
        fn drop(&mut self) {
            // SAFETY: AllocateAndInitializeSid가 준 SID를 한 번만 놓는다
            unsafe { FreeSid(self.0) };
        }
    }

    /// 놓이면 CloseHandle
    struct Owned(HANDLE);

    impl Drop for Owned {
        fn drop(&mut self) {
            if !self.0.is_null() {
                // SAFETY: 이 구조체가 가진 핸들을 한 번만 닫는다
                unsafe { CloseHandle(self.0) };
            }
        }
    }

    /// Administrators·Power Users — PostgreSQL이 거부하는 두 그룹(`pgwin32_is_admin`)
    fn groups() -> io::Result<[Sid; 2]> {
        Ok([
            Sid::builtin(DOMAIN_ALIAS_RID_ADMINS)?,
            Sid::builtin(DOMAIN_ALIAS_RID_POWER_USERS)?,
        ])
    }

    /// 지금 토큰에 두 그룹 가운데 하나가 켜져 있나 — UAC가 거른 토큰에서는 거부 전용이라 아니다
    fn is_admin() -> io::Result<bool> {
        for sid in groups()? {
            let mut member: BOOL = 0;
            // SAFETY: 토큰 NULL은 이 스레드의 토큰, sid는 살아 있는 SID
            if unsafe { CheckTokenMembership(null_mut(), sid.0, &mut member) } == 0 {
                return Err(io::Error::last_os_error());
            }
            if member != 0 {
                return Ok(true);
            }
        }
        Ok(false)
    }

    /// 토큰 정보 — 구조체를 그대로 읽을 수 있게 8바이트 맞춤 버퍼로
    fn token_info(token: HANDLE, class: TOKEN_INFORMATION_CLASS) -> io::Result<Vec<u64>> {
        let mut size = 0u32;
        // SAFETY: 크기만 묻는다 — 버퍼 없이 부르면 실패하고 size를 채운다
        unsafe { GetTokenInformation(token, class, null_mut(), 0, &mut size) };
        if size == 0 {
            return Err(io::Error::last_os_error());
        }
        let mut buf = vec![0u64; (size as usize).div_ceil(8)];
        // SAFETY: buf는 size 바이트 이상
        if unsafe { GetTokenInformation(token, class, buf.as_mut_ptr().cast(), size, &mut size) }
            == 0
        {
            return Err(io::Error::last_os_error());
        }
        Ok(buf)
    }

    /// 토큰의 기본 DACL에 지금 사용자를 더한다 — 관리자 토큰의 기본 DACL은 Administrators·SYSTEM뿐이라
    /// 그 그룹을 거부 전용으로 바꾸면 자기가 만든 파이프·프로세스에도 닿지 못한다(PostgreSQL `AddUserToTokenDacl`)
    fn add_user_to_dacl(token: HANDLE) -> io::Result<()> {
        let dacl = token_info(token, TokenDefaultDacl)?;
        let user = token_info(token, TokenUser)?;
        // SAFETY: GetTokenInformation이 버퍼 첫머리에 TOKEN_DEFAULT_DACL·TOKEN_USER를 채웠다 — 가리키는 곳도 그 버퍼 안
        let (old, sid) = unsafe {
            (
                (*dacl.as_ptr().cast::<TOKEN_DEFAULT_DACL>()).DefaultDacl,
                (*user.as_ptr().cast::<TOKEN_USER>()).User.Sid,
            )
        };
        if old.is_null() {
            return Ok(()); // 기본 DACL이 없으면 막히는 것도 없다
        }
        let mut info = ACL_SIZE_INFORMATION::default();
        // SAFETY: old는 살아 있는 ACL · info는 지역 변수
        if unsafe {
            GetAclInformation(
                old,
                (&mut info as *mut ACL_SIZE_INFORMATION).cast(),
                size_of::<ACL_SIZE_INFORMATION>() as u32,
                AclSizeInformation,
            )
        } == 0
        {
            return Err(io::Error::last_os_error());
        }
        // 새 ACE = ACCESS_ALLOWED_ACE에서 SidStart 자리를 SID로 바꾼 크기
        // SAFETY: sid는 user 버퍼 안의 SID
        let size = info.AclBytesInUse + size_of::<ACCESS_ALLOWED_ACE>() as u32
            - size_of::<u32>() as u32
            + unsafe { GetLengthSid(sid) };
        let mut buf = vec![0u64; (size as usize).div_ceil(8)];
        let acl = buf.as_mut_ptr().cast::<ACL>();
        // SAFETY: acl은 size 바이트 이상인 버퍼 · old의 ACE를 차례로 옮기고 사용자 ACE를 끝에 더한다
        unsafe {
            if InitializeAcl(acl, size, ACL_REVISION) == 0 {
                return Err(io::Error::last_os_error());
            }
            for i in 0..info.AceCount {
                let mut ace = null_mut();
                if GetAce(old, i, &mut ace) == 0 {
                    return Err(io::Error::last_os_error());
                }
                let len = (*ace.cast::<ACE_HEADER>()).AceSize as u32;
                if AddAce(acl, ACL_REVISION, u32::MAX, ace, len) == 0 {
                    return Err(io::Error::last_os_error());
                }
            }
            if AddAccessAllowedAceEx(acl, ACL_REVISION, OBJECT_INHERIT_ACE, GENERIC_ALL, sid) == 0 {
                return Err(io::Error::last_os_error());
            }
            let new = TOKEN_DEFAULT_DACL { DefaultDacl: acl };
            if SetTokenInformation(
                token,
                TokenDefaultDacl,
                (&new as *const TOKEN_DEFAULT_DACL).cast(),
                size_of::<TOKEN_DEFAULT_DACL>() as u32,
            ) == 0
            {
                return Err(io::Error::last_os_error());
            }
        }
        Ok(())
    }

    /// 콘솔의 Ctrl+C는 자식이 받아 끄는 순서를 탄다 — 이 프로세스는 기다리기만 한다
    unsafe extern "system" fn ignore_ctrl(_: u32) -> BOOL {
        1
    }

    fn rerun_restricted() -> io::Result<u32> {
        let mut token: HANDLE = null_mut();
        // SAFETY: 자기 프로세스의 의사 핸들 · token은 지역 변수
        if unsafe { OpenProcessToken(GetCurrentProcess(), TOKEN_ALL_ACCESS, &mut token) } == 0 {
            return Err(io::Error::last_os_error());
        }
        let token = Owned(token);
        let sids = groups()?;
        let disable = [
            SID_AND_ATTRIBUTES {
                Sid: sids[0].0,
                Attributes: 0,
            },
            SID_AND_ATTRIBUTES {
                Sid: sids[1].0,
                Attributes: 0,
            },
        ];
        let mut restricted: HANDLE = null_mut();
        // SAFETY: disable은 이 호출 동안 살아 있는 SID 둘을 가리킨다
        if unsafe {
            CreateRestrictedToken(
                token.0,
                DISABLE_MAX_PRIVILEGE,
                disable.len() as u32,
                disable.as_ptr(),
                0,
                null(),
                0,
                null(),
                &mut restricted,
            )
        } == 0
        {
            return Err(io::Error::last_os_error());
        }
        let restricted = Owned(restricted);
        add_user_to_dacl(restricted.0)?;

        // 명령줄은 CreateProcessW가 고쳐 쓸 수 있는 버퍼여야 한다
        // SAFETY: GetCommandLineW는 프로세스가 끝날 때까지 사는 NUL로 끝나는 문자열을 준다
        let mut cmdline = unsafe {
            let p = GetCommandLineW();
            let mut len = 0;
            while *p.add(len) != 0 {
                len += 1;
            }
            let mut v = std::slice::from_raw_parts(p, len).to_vec();
            v.push(0);
            v
        };
        // SAFETY: main이 tokio를 만들기 전 — 스레드가 하나다
        unsafe { std::env::set_var(RESTRICTED_ENV, "1") };

        let mut si = STARTUPINFOW {
            cb: size_of::<STARTUPINFOW>() as u32,
            dwFlags: STARTF_USESTDHANDLES,
            ..Default::default()
        };
        // 표준 입력·출력·오류를 물려준다 — 물려줄 수 있게 표시한다(없거나 잘못된 핸들은 그대로)
        // SAFETY: GetStdHandle이 준 핸들의 상속 표시만 바꾼다
        unsafe {
            si.hStdInput = GetStdHandle(STD_INPUT_HANDLE);
            si.hStdOutput = GetStdHandle(STD_OUTPUT_HANDLE);
            si.hStdError = GetStdHandle(STD_ERROR_HANDLE);
            for h in [si.hStdInput, si.hStdOutput, si.hStdError] {
                if !h.is_null() && h as isize != -1 {
                    SetHandleInformation(h, HANDLE_FLAG_INHERIT, HANDLE_FLAG_INHERIT);
                }
            }
        }
        let mut pi = PROCESS_INFORMATION::default();
        // SAFETY: restricted는 자기 토큰을 줄인 것(SE_ASSIGNPRIMARYTOKEN 없이 된다) · cmdline·si·pi는 살아 있다
        if unsafe {
            CreateProcessAsUserW(
                restricted.0,
                null(),
                cmdline.as_mut_ptr(),
                null(),
                null(),
                1,
                0,
                null(),
                null(),
                &si,
                &mut pi,
            )
        } == 0
        {
            return Err(io::Error::last_os_error());
        }
        let (process, _thread) = (Owned(pi.hProcess), Owned(pi.hThread));
        // SAFETY: 처리기는 'static 함수
        unsafe { SetConsoleCtrlHandler(Some(ignore_ctrl), 1) };
        // 자식이 이미 돈다 — 여기서부터 실패해도 그대로 켜지 않는다(둘이 켜진다), 끝 코드 1
        // SAFETY: process는 방금 만든 자식의 핸들
        if unsafe { WaitForSingleObject(process.0, INFINITE) } != WAIT_OBJECT_0 {
            eprintln!(
                "다시 켠 싱크독_로컬을 기다리지 못했다 — {}",
                io::Error::last_os_error()
            );
            return Ok(1);
        }
        let mut code = 1u32;
        // SAFETY: 끝난 자식의 핸들 · code는 지역 변수
        if unsafe { GetExitCodeProcess(process.0, &mut code) } == 0 {
            eprintln!(
                "다시 켠 싱크독_로컬의 끝 코드를 못 읽었다 — {}",
                io::Error::last_os_error()
            );
            return Ok(1);
        }
        Ok(code)
    }
}
