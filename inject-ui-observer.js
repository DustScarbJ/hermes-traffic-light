/**
 * Hermes Traffic Light — UI State Observer
 * ==========================================
 *
 * Paste this entire script into Hermes DevTools Console (F12 → Console tab).
 * Monitors Hermes sidebar for real-time state changes and sends events
 * to HermesTrafficLight via HTTP POST to port 18888.
 *
 * 状态检测方式（不依赖多语言文本 / 不依赖 class name 精确值）:
 *   1. React fiber 探针 — 读取组件内部 busy/needsInput 状态
 *   2. DOM 结构探针 — 检查 sidebar 子元素结构变化
 *   3. 降级策略 — 仅当以上均失效时回归 class pattern 匹配
 *
 * 注入方式:
 *   1. 在 Hermes 窗口按 F12 打开 DevTools
 *   2. 切换到 Console 标签
 *   3. 粘贴本脚本并回车
 */

(function () {
  'use strict';

  const TL_HOST = 'http://127.0.0.1:18888';
  const DEBOUNCE_MS = 300;
  const CHECK_INTERVAL_MS = 1000; // 兜底心跳检测

  // ── 发送事件到信号灯 ──
  function send(event, detail = {}) {
    const body = JSON.stringify({ event, source: 'ui', detail, ts: Date.now() });
    fetch(`${TL_HOST}/event`, {
      method: 'POST',
      mode: 'no-cors',
      headers: { 'Content-Type': 'application/json' },
      body,
    }).catch(() => {});
  }

  // ── 状态缓存 + debounce ──
  let prevState = null;
  let debounceTimer = null;

  function reportState(newState, label) {
    if (newState === prevState) return;
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      prevState = newState;
      console.log(`[HermesTL] ${label} → ${newState}`);
      send(newState);
    }, DEBOUNCE_MS);
  }

  // ── 探针 1: React fiber 内部状态 ──
  function probeReactFiber() {
    // 在 React 18+ 中, DOM 元素上有 __reactFiber$... 或 __reactProps$... 属性
    // 从 sidebar 或 body 遍历 fiber 树寻找 session state
    const root = document.getElementById('root') || document.body;
    const key = Object.keys(root).find(k => k.startsWith('__reactFiber'));
    if (!key) return null;

    let fiber = root[key];
    let depth = 0;
    while (fiber && depth < 500) {
      const memoizedState = fiber.memoizedState;
      if (memoizedState) {
        // 扫描 fiber 的 state 链, 找包含 busy/needsInput 的节点
        let stateNode = memoizedState;
        while (stateNode) {
          const q = stateNode.queue;
          if (q && q.lastRenderedState) {
            const s = q.lastRenderedState;
            // 有的组件状态是 {busy, needsInput, ...}
            if (typeof s.busy === 'boolean' || typeof s.needsInput === 'boolean') {
              return { busy: !!s.busy, needsInput: !!s.needsInput };
            }
            // 有的在 pendingBranchGroup / streamId 等字段旁
            if (typeof s.streamId === 'string' || typeof s.turnStartedAt === 'number') {
              if (s.busy === true) return { busy: true, needsInput: false };
              if (s.needsInput === true) return { busy: false, needsInput: true };
            }
          }
          // states 链表: 注意有的 React 版本用 .next 有的用 .queue
          stateNode = stateNode.next || (stateNode.queue ? null : null);
          // 安全终止
          if (!stateNode || stateNode === memoizedState) break;
        }
      }
      fiber = fiber.child || fiber.sibling || fiber.return;
      if (fiber && fiber.sibling && !fiber.child) {
        let f = fiber;
        while (f && !f.sibling && f.return) f = f.return;
        fiber = f ? f.sibling : null;
      }
      depth++;
    }
    return null;
  }

  // ── 探针 2: DOM 结构检测 ──
  function probeDOM() {
    // 策略 A: 检测 Stop 按钮（Agent 正在执行时 Hermes 显示停止按钮）
    const stopBtn = document.querySelector(
      '[class*="stop"],[aria-label*="stop" i],[class*="interrupt"]'
    );
    if (stopBtn && stopBtn.offsetParent !== null) {
      return 'busy';
    }

    // 策略 B: 检测 Clarify 弹窗（等待用户确认时显示）
    const clarifyDialog = document.querySelector(
      '[class*="clarify"],[class*="clarify-overlay"],' +
      '[class*="clarify-dialog"],[role="dialog"]'
    );
    if (clarifyDialog && clarifyDialog.offsetParent !== null) {
      // 检查弹窗内容是否含 clarify 特征
      const txt = clarifyDialog.textContent || '';
      if (/clarify|明确化|確認|choice|select|choose|选项/i.test(txt)) {
        return 'needs_input';
      }
    }

    // 策略 C: 检测 Composer（输入框）状态
    const composer = document.querySelector(
      '[class*="composer"] textarea, ' +
      '[class*="composer"] [contenteditable], ' +
      '[class*="input-area"] textarea, ' +
      '[class*="message-input"]'
    );
    if (composer) {
      // 输入框 disabled = Hermes 正在执行
      if (composer.disabled || composer.getAttribute('aria-disabled') === 'true') {
        return 'busy';
      }
      // 输入框可输入 = 空闲或等待用户
      // 再检查有没有 clarify 弹窗
      return 'idle';
    }

    // 策略 D: 检测 Sidebar 中存在状态圆点变化
    const statusDots = document.querySelectorAll(
      '[class*="status"] circle, [class*="status"][class*="dot"], ' +
      '[class*="indicator"][class*="running"], ' +
      '[class*="indicator"][class*="working"]'
    );
    if (statusDots.length > 0) {
      for (const dot of statusDots) {
        if (dot.offsetParent === null) continue;
        const cls = dot.className || dot.parentElement?.className || '';
        if (/\b(running|thinking|working|spinning|loading)\b/i.test(cls)) return 'busy';
        if (/\b(wait|input|clarify)\b/i.test(cls)) return 'needs_input';
      }
    }

    // 策略 E: 兜底 — 检查 Hermes 页面是否加载完成
    const mainArea = document.querySelector(
      '[class*="main"], [class*="content"], [class*="layout"]'
    );
    if (mainArea) return 'idle';

    // 无任何 UI 元素 → 可能没有活跃窗口
    return null;
  }

  // ── 主检测: 合并探针结果 ──
  function sniffState() {
    // 先用 fiber 探针
    const fiberState = probeReactFiber();
    if (fiberState) {
      if (fiberState.busy) return 'busy';
      if (fiberState.needsInput) return 'needs_input';
      return 'idle';
    }

    // fiber 探针失败 → DOM 探针
    return probeDOM();
  }

  // ── MutationObserver ──
  let observer = null;

  function startObserving() {
    const target =
      document.querySelector('.sidebar') ||
      document.querySelector('[class*="sidebar"]') ||
      document.querySelector('#root') ||
      document.body;

    if (!target) {
      console.warn('[HermesTL] Target not found, retrying in 2s...');
      setTimeout(startObserving, 2000);
      return;
    }

    observer = new MutationObserver(() => {
      const state = sniffState();
      if (state) reportState(state, 'MutationObserver');
    });

    observer.observe(target, {
      attributes: true,
      childList: true,
      subtree: true,
      characterData: false,
    });

    // 兜底定期检测
    setInterval(() => {
      const state = sniffState();
      if (state) reportState(state, 'heartbeat');
    }, CHECK_INTERVAL_MS);

    // 初始状态
    setTimeout(() => {
      const init = sniffState();
      if (init) reportState(init, 'init');
    }, 500);

    console.log('[HermesTL] ✅ UI State Observer started — watching', target.tagName);
  }

  // ── 启动 ──
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', startObserving);
  } else {
    startObserving();
  }

  console.log('[HermesTL] Loaded — monitoring Hermes UI state in real-time');
})();
