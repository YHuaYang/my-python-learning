# TODO

## 待办

- [ ] 项目排序：后台加「按当前顺序重编号」按钮
      原因：`sort_order` 允许重复，现在两个项目都是 1，
      排序靠 `-created_date` 兜底，不是手控。加 action 一键重编号成 1,2,3…

- [ ] Markdown 编辑器换成 Toast UI Editor（用户选定方案 B）
      原因：用户痛点是「得背 Markdown 语法」。EasyMDE 本质是
      「写源码 + 预览」，不能解决。Toast UI 有 WYSIWYG 模式，
      选中文字点按钮即可。
      参考项目 `XinghuisamaBlogs` 用的是 TipTap 全套
      （约 30 个 npm 包），与我们 Django Admin 架构不兼容，不能照抄。

- [ ] 图片上传接口（配合编辑器）
      存 `media/uploads/`。安全要点：
      - `@login_required` + `is_staff` 双重检查
      - 用 Pillow 真解码验证是图片，不查扩展名
      - 禁止 SVG（可内嵌脚本）
      - 单文件 5MB + 尺寸上限
      - 返回 JSON 给编辑器插入

- [ ] 部署上线
      阻塞项：`media/` 在生产环境没有托管方案
      （现在靠 `DEBUG=True` 下的 `static()`，上线后所有上传图片会 404）。
      其他：4 个 HTTPS 安全项、`Site.domain` 改真实域名、SQLite 换 PostgreSQL。

- [ ] 手机端响应式（用户明确暂缓，动前先问）

- [ ] FastAPI 新闻服务（规划文档第 5-6 周）

- [ ] React 新闻页 `/news/`（规划文档第 7-9 周）

## 已完成

- [x] 后台换肤为 unfold（2026-11-23）
- [x] 访问统计 + 仪表盘（2026-11-23）
- [x] 后台全中文化 + unfold 语言包（2026-11-23）
- [x] 后台表单控件换 unfold 基类（2026-11-23）
- [x] robots.txt（2026-11-23）
- [x] 项目封面图上传（2026-11-22）
- [x] 头像上传（2026-11-22）
- [x] 首页 6 篇上限 + 归档页（2026-11-22）
- [x] 留言板 + 审核 + 限流（2026-11-10）
