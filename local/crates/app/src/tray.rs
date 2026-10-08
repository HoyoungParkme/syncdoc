//! 트레이 — 열기·끝내기 (SYNC-MS-012#tray.run · SYNC-INFRA-001 9.1·9.2, 카드 L4).
//! 윈도는 트레이가 만든 스레드에서 메시지를 돌려야 한다 — 그래서 메인 스레드가 트레이 차지이고 tokio는 일꾼 스레드에서 돈다.
//! 리눅스는 StatusNotifierItem(D-Bus, GTK 없이) — 메인 스레드는 끝나기를 기다리기만 한다.

use std::sync::mpsc;
use std::sync::{Arc, Mutex};

use syncdoc_core::errors::Problem;
use tokio::runtime::Runtime;
use tokio::sync::oneshot;
use tray_icon::menu::{Menu, MenuEvent, MenuItem};
use tray_icon::{Icon, MouseButton, TrayIcon, TrayIconBuilder, TrayIconEvent};

use crate::runtime::{self, Args};

/// 트레이 아이콘 32×32 RGBA — `cargo xtask icon`이 `packaging/icon.svg`에서 만든다
const ICON: &[u8] = include_bytes!("../../../packaging/tray.rgba");

/// `runtime.run`과 트레이 사이 — 켜진 주소는 트레이로, 「끝내기」는 runtime으로
pub struct TrayLink {
    pub url: mpsc::Sender<String>,
    pub quit: oneshot::Receiver<()>,
}

/// SYNC-MS-012#tray.run
pub fn run(rt: &Runtime, args: Args) -> Result<(), Problem> {
    let main = loop_handle();
    let waker = main.waker();
    let (url_tx, url_rx) = mpsc::channel();
    let (quit_tx, quit_rx) = oneshot::channel();
    let (done_tx, done_rx) = mpsc::channel();
    rt.spawn(async move {
        let result = runtime::run(
            args,
            Some(TrayLink {
                url: url_tx,
                quit: quit_rx,
            }),
        )
        .await;
        let _ = done_tx.send(result);
        waker.wake();
    });
    // 주소가 오기 전에 끝나면(켜기 실패·두 번째 실행) 트레이 없이 그 결과
    let Ok(url) = url_rx.recv() else {
        return done_rx.recv().unwrap_or(Ok(()));
    };
    let quit = Arc::new(Mutex::new(Some(quit_tx)));
    let _tray = match build(&url, quit) {
        Ok(t) => Some(t),
        Err(e) => {
            tracing::warn!("트레이를 못 만들었다 — 트레이 없이 간다: {e}");
            None
        }
    };
    main.pump();
    done_rx.recv().unwrap_or(Ok(()))
}

/// 메뉴 「열기」·「끝내기」, 아이콘 두 번 누르기 = 열기
fn build(url: &str, quit: Arc<Mutex<Option<oneshot::Sender<()>>>>) -> Result<TrayIcon, String> {
    let open = MenuItem::new("열기", true, None);
    let end = MenuItem::new("끝내기", true, None);
    let menu = Menu::new();
    menu.append_items(&[&open, &end])
        .map_err(|e| e.to_string())?;
    let (open_id, end_id) = (open.id().clone(), end.id().clone());
    let target = url.to_string();
    MenuEvent::set_event_handler(Some(move |e: MenuEvent| {
        if e.id == open_id {
            open_browser(&target);
        } else if e.id == end_id
            && let Some(tx) = quit.lock().ok().and_then(|mut q| q.take())
        {
            let _ = tx.send(());
        }
    }));
    let target = url.to_string();
    TrayIconEvent::set_event_handler(Some(move |e: TrayIconEvent| {
        if let TrayIconEvent::DoubleClick {
            button: MouseButton::Left,
            ..
        } = e
        {
            open_browser(&target);
        }
    }));
    let icon = Icon::from_rgba(ICON.to_vec(), 32, 32).map_err(|e| e.to_string())?;
    TrayIconBuilder::new()
        .with_menu(Box::new(menu))
        .with_tooltip(format!("싱크독_로컬 — {url}"))
        .with_icon(icon)
        .build()
        .map_err(|e| e.to_string())
}

fn open_browser(url: &str) {
    if let Err(e) = webbrowser::open(url) {
        tracing::warn!("브라우저를 못 열었다 — {url}: {e}");
    }
}

/// 메인 스레드의 루프 — 윈도는 tao 이벤트 루프(트레이 창의 메시지를 돌린다), 그 밖은 기다리기만
struct LoopHandle {
    #[cfg(windows)]
    event_loop: tao::event_loop::EventLoop<()>,
}

/// 일꾼이 메인 루프를 깨운다 — runtime.run이 끝났다
#[derive(Clone)]
struct Waker {
    #[cfg(windows)]
    proxy: tao::event_loop::EventLoopProxy<()>,
}

#[cfg(windows)]
fn loop_handle() -> LoopHandle {
    LoopHandle {
        event_loop: tao::event_loop::EventLoopBuilder::<()>::with_user_event().build(),
    }
}

#[cfg(not(windows))]
fn loop_handle() -> LoopHandle {
    LoopHandle {}
}

impl LoopHandle {
    fn waker(&self) -> Waker {
        Waker {
            #[cfg(windows)]
            proxy: self.event_loop.create_proxy(),
        }
    }

    /// 메인 스레드 — 윈도는 깨울 때까지 이벤트를 돌린다
    fn pump(self) {
        #[cfg(windows)]
        {
            use tao::event::Event;
            use tao::event_loop::ControlFlow;
            use tao::platform::run_return::EventLoopExtRunReturn;
            let mut event_loop = self.event_loop;
            event_loop.run_return(|event, _, flow| {
                *flow = match event {
                    Event::UserEvent(()) => ControlFlow::Exit,
                    _ => ControlFlow::Wait,
                };
            });
        }
    }
}

impl Waker {
    fn wake(&self) {
        #[cfg(windows)]
        {
            let _ = self.proxy.send_event(());
        }
    }
}
