# TODO

## 待办

- [ ] **服务器到手后的实际部署**（配置已备好，等服务器）
      服务器：腾讯云 4核4G / Ubuntu 24.04 LTS / 只上线一年
      按 `deploy/README.md` 走，五个关键点：
      1. 未备案时只能用 IP 访问（README 第十一节有临时配置）
      2. 改三处 `example.com`：nginx.conf / deploy.sh / .env
      3. DNS 解析成功后才能申请证书（`dig 域名 +short` 验证）
      4. 拿到证书后 `.env` 设 `USE_HTTPS=True` 并重启
      5. 后台改 `Site.domain` 为真实域名，否则 sitemap 指向 127.0.0.1

- [ ] 到期前备份数据（服务器只用一年）
      数据库与上传的图片只在服务器上，代码在 git 里不用管。
      ```bash
      sudo -u www-data sqlite3 /var/www/mysite/db.sqlite3 ".backup /root/mysite.sqlite3"
      sudo tar -czf /root/media.tar.gz -C /var/www/mysite media/
      ```

- [ ] 手机端响应式（用户明确暂缓，动前先问）

- [ ] FastAPI 新闻服务（规划文档第 5-6 周）

- [ ] React 新闻页 `/news/`（规划文档第 7-9 周）

## 已完成

- [x] 生产部署配置（2026-11-24）
      gunicorn.conf.py / mysite.service / nginx.conf（含 /media/ 托管）
      deploy.sh / update.sh / README.md
      修复 collectstatic 死锁：Media 类的 static() 改用 lazy()
      check --deploy 从 4 个警告变为 0

- [x] 编辑器图片上传接口（2026-11-24）
      七层防护，12 个测试覆盖：权限、方法、大小、真解码、
      尺寸、禁 SVG、uuid 重命名

- [x] 修复编辑器工具栏污染正文（2026-11-24）
      根因是无有效选区时 Toast UI 会插入孤立 **，
      而孤立的 ** 会让下次渲染抛 RangeError 把编辑器搞崩
      修法：拦截无选区/选区在编辑器外的行内格式按钮

- [x] 工具栏提示中文化（2026-11-24）
      根因：只写 language: 'zh-CN' 不够，必须导入语言包文件
      `import '@toast-ui/editor/dist/i18n/zh-cn'`

- [x] 清理开发期测试内容（2026-11-24）
      清空 Post/Project/WeeklyProgress/GuestbookMessage/VisitLog/Profile
      保留 Category（3）与 Tag（2）作为结构数据
      保留 media/ 下用户上传的图片

- [x] 项目排序重编号按钮（2026-11-23）
- [x] Toast UI Markdown 编辑器（2026-11-23）
      覆盖 Post.text / Project.description / WeeklyProgress.content
- [x] 后台换肤为 unfold（2026-11-23）
- [x] 访问统计 + 仪表盘（2026-11-23）
- [x] 后台全中文化 + unfold 语言包（2026-11-23）
- [x] 后台表单控件换 unfold 基类（2026-11-23）
- [x] robots.txt（2026-11-23）
- [x] 项目封面图上传（2026-11-22）
- [x] 头像上传（2026-11-22）
- [x] 首页 6 篇上限 + 归档页（2026-11-22）
- [x] 留言板 + 审核 + 限流（2026-11-10）
