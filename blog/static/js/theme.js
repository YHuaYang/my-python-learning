// 暗色模式切换。
//
// 设计优先级：localStorage 里的手动选择 > 系统偏好
// 首次访问时跟随系统，用户点过切换后就记住他的选择。
//
// 为什么要单独一个文件：base.html 里已经有一段同步执行的防闪屏脚本，
// 那一段必须留在 <head> 内联（等外部 JS 加载完再执行会先闪白屏）。
// 这里只放点击事件绑定，延迟加载无影响。

(function () {
    'use strict';

    var STORAGE_KEY = 'theme';

    function getStored() {
        try {
            return localStorage.getItem(STORAGE_KEY);
        } catch (e) {
            // 隐私模式下 localStorage 可能抛异常，降级为「不记忆」
            return null;
        }
    }

    function setStored(value) {
        try {
            localStorage.setItem(STORAGE_KEY, value);
        } catch (e) {
            // 同上，存不了就算了，不影响当前页面的切换
        }
    }

    function prefersDark() {
        return window.matchMedia &&
            window.matchMedia('(prefers-color-scheme: dark)').matches;
    }

    function apply(isDark) {
        document.documentElement.classList.toggle('dark', isDark);
        updateButton(isDark);
    }

    function updateButton(isDark) {
        var btn = document.getElementById('theme-toggle');
        if (!btn) {
            return;
        }
        // 按钮显示的是「点击后会发生什么」，所以暗色时显示太阳
        btn.textContent = isDark ? '☀' : '☾';
        btn.setAttribute('aria-label', isDark ? '切换到亮色模式' : '切换到暗色模式');
        btn.setAttribute('title', isDark ? '切换到亮色模式' : '切换到暗色模式');
    }

    function currentIsDark() {
        return document.documentElement.classList.contains('dark');
    }

    document.addEventListener('DOMContentLoaded', function () {
        // <head> 里的内联脚本已经设好了初始状态，这里只同步按钮外观
        updateButton(currentIsDark());

        var btn = document.getElementById('theme-toggle');
        if (!btn) {
            return;
        }
        btn.addEventListener('click', function () {
            var next = !currentIsDark();
            apply(next);
            setStored(next ? 'dark' : 'light');
        });
    });

    // 用户没手动选过时，跟随系统设置的实时变化
    if (window.matchMedia) {
        window.matchMedia('(prefers-color-scheme: dark)')
            .addEventListener('change', function (e) {
                if (getStored() === null) {
                    apply(e.matches);
                }
            });
    }
})();
