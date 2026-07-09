# feishu_install_guidance
# 飞书 CLI：给 Agent 一双操作飞书的手

你的 AI Agent 很聪明，但它看不到你的日历，读不了你的群聊，打不开你的文档。它就像一个能力很强但没有手的人，只能跟你聊天，不能帮你干活。

飞书 CLI 就是给 Agent 的那双手。装上之后，你的 Agent 可以直接读你的飞书消息、查你的日历、写文档、建多维表格、搜知识库、发邮件。不是生成一段文字让你复制粘贴，而是直接在飞书里帮你把事情办了。

以前是你操作飞书，现在是 AI 操作飞书，你只管拍板。

## GitHub 开源

飞书 CLI 现已面向所有用户开源。无论你是想让现有的 Agent 拥有操作飞书的能力，还是希望围绕飞书构建全新的自动化工作流，现在就给你的 AI 装上这双手：

👉**获取代码**：**[GitHub 开源地址](https://github.com/larksuite/cli)**

## 🚀 快速开始

### 1. 一键安装与配置

- **方式一**：手动安装。在终端中输入以下命令完成安装：

```
 	npx @larksuite/cli@latest install
  ```
- **方式二**： Agent 自动安装。将以下指令直接复制发送给你的 AI 工具（如 TRAE、Cursor、Codex、Claude Code），让它替你完成安装：

```
  帮我安装飞书 CLI：https://open.feishu.cn/document/no_class/mcp-archive/feishu-cli-installation-guide.md
  ```
- 配置完成后，**请重启你的 AI 工具** 以确保所有 Skills 完整加载。
- 配置应用时，默认会创建一个新应用，也可以选择一个已有应用。

### 2. （可选）完成用户授权

飞书 CLI 支持两种工作模式，你可以按需选择：

- **以你的身份操作**：AI 可以访问你个人的日历、消息、文档，并以你的名义执行操作。需要完成一次用户授权——运行下方命令后，打开链接在飞书中确认即可。（如果暂时跳过，后续 AI 在需要访问你个人数据时，也会自动发起授权提示。）

```
  lark-cli auth login
  ```

![image.png](//sf3-cn.feishucdn.com/obj/open-platform-opendoc/2034b9fa679abfc3e6db50bf2e51e8de_PYvoUOJ0Ed.png?height=1004&lazyload=true&maxWidth=450&width=1866)

- **不授权，直接使用**：AI 仍然可以执行发消息、创建文档等操作，但无法访问你的个人数据（如你的日程、私信、收件箱）。

### 🎉 3. 开启你的第一个任务

打开你的 AI Agent 工具（如 TRAE、Cursor、Codex、Claude Code），在对话框中输入你的需求：

```
帮我创建一篇云文档，介绍飞书 CLI 的能力有哪些，以及基于你对我的了解，我可以先开始用哪些能力
```

## 🎬 用户案例

### 场景 1：会后待办一键清

会议里随口提一句“我之后把那个文档发给你”，开完会就忘了。**现在 agent 直接从妙记里把这个待办识别出来，帮你把文档发了、会约了、调研做了。你只需要确认一下，剩下的它全干。**

比如会上说要给谁发东西，agent 帮你发。说回头试一个新产品，agent 把链接找到发给你。说要约 follow up，agent 查完日历直接把会建好，做之前会先让你过目。

**进阶玩法：Wake Word 指令** ：
你可以设置一个触发词（比如“龙虾龙虾”），开会的时候随口说“龙虾龙虾，帮我把这个方案整理成文档发给老板”，会后 agent 自动从妙记逐字稿里识别出你的指令，提取为最高优先级待办，直接执行。你不需要记住自己在会上说了什么，agent 替你记着。

| 用户输入提示词        | AI 输出         |
| --------- | --------------- |
| 读一下这个妙记，然后把里面的待办提取出来，直接帮我办了。做之前给我看一下你的计划。| ![img_v3_0210c_2c046495-8e7d-47bf-a092-181db00c545g.jpg](//sf3-cn.feishucdn.com/obj/open-platform-opendoc/1b004eff7274926677a7ab3b41b1808a_gOEMzuKsca.jpg?height=366&lazyload=true&maxWidth=360&width=1160)<br>![img_v3_0210c_277bfe78-4b55-4a80-a902-857ac1b13d2g.jpg](//sf3-cn.feishucdn.com/obj/open-platform-opendoc/cb4e5bcce4535e144382f672734ae3f6_aWVXIxe2PX.jpg?height=726&lazyload=true&maxWidth=350&width=2178)<br>![img_v3_0210c_3f1fefd7-66b0-4927-8f6d-f9cbcfbde8fg.jpg](//sf3-cn.feishucdn.com/obj/open-platform-opendoc/ebc8b80dc037740fff72d8a3bd105bd5_IQgj3q3jhe.jpg?height=966&lazyload=true&maxWidth=330&width=1304) | 

### 场景 2：人机共创与文档评审

写方案要反复和 AI 对话、复制粘贴、格式排版，效率低。现在有几种玩法：

- **AI 起草，你来把关。** AI 在飞书文档里直接创建初稿，你在文档里用评论提修改意见，AI 读取评论、修改正文，持续迭代，全程不离开飞书。

| 用户输入        | AI 输出         |
    | --------- | --------------- |
    | 提示词 ：根据我的所在部门、飞书消息、飞书云文档、日程等信息，帮我创建一篇飞书云文档，写一篇个人使用说明书。 | AI 创作文档：<br>![image.png](//sf3-cn.feishucdn.com/obj/open-platform-opendoc/9e91263edaf91bcfc51026b5942a8035_fUyf1Srklt.png?height=803&lazyload=true&maxWidth=350&width=1280) | 
    |提示词 ：{{文档链接}} 根据我的评论修改文档，修改后，用划词评论标识出修改点。<br><br> 用户留评论：![image.png](//sf3-cn.feishucdn.com/obj/open-platform-opendoc/4181f87dc4e8f4ec670088ad45727bca_M6Exa1tGAS.png?height=803&lazyload=true&maxWidth=320&width=1280) |AI 修改文档并高亮改动点：<br> ![image.png](//sf3-cn.feishucdn.com/obj/open-platform-opendoc/3ca0bb0c2a47d873be9f8371c540bfa4_8WQaN6ycd1.png?height=803&lazyload=true&maxWidth=350&width=1280)|

- **你起草，AI 当审稿人。** 你写好初稿后，让 AI 阅读全文，以评论的形式指出逻辑漏洞、数据缺失、表述不清的地方，和你在评论区讨论。就像有一个随时在线的资深同事帮你 review。

| 用户输入提示词        | AI 评审文档        |
  | --------- | --------------- |
  | {{文档链接}}阅读一下这篇文档，看下作为提供给外部用户的说明文档，是否足够清晰、简洁。不要直接改文档，只把你觉得有优化空间的位置划词评论出来，在评论里写上修改意见。 | <br>![image.png](//sf3-cn.feishucdn.com/obj/open-platform-opendoc/5a3d00bcfea045bdb21458e5ca0bdc00_t6A4K07CNp.png?height=803&lazyload=true&width=1280) | 

- **Markdown 无缝转飞书文档。** 你在 AI 工具里用 Markdown 写了一篇技术方案，想发给同事看？直接说"把这个 Markdown 创建成飞书文档"，agent 自动转换格式，高亮块、表格、代码块、分栏全部保留。反过来也行，从飞书文档导出成 Markdown。

| 用户输入提示词        | AI 输出         |
  | --------- | --------------- |
  | 把这篇 Markdown 内容创建成飞书文档，排版要好看 | ![image.png](//sf3-cn.feishucdn.com/obj/open-platform-opendoc/5d33f8b2bc3bb6f24c8570cc5746f8a8_naNRl72QqL.png?height=606&lazyload=true&maxWidth=300&width=1582)<br>![image.png](//sf3-cn.feishucdn.com/obj/open-platform-opendoc/b33a3808794b0389100d71790822ad44_ux6ZInSsKe.png?height=1014&lazyload=true&maxWidth=330&width=1712)| 

### 场景 3：跨时区智能约会

约一个 5 人会议，手动翻日历找共同空闲时间，来回沟通 20 分钟。团队还分布在不同时区，手动算时差更头疼。现在告诉 AI "帮我约这个群里的人下周开个会"，AI 自动拉群成员、查每个人的日历空闲、考虑所有人的时区，推荐几个"所有人都在合理工作时间"的选项。你选一个，会就建好了。

| 用户输入提示词       | AI 自动约会         |
| --------- | --------------- |
| 帮我看一下【XX】群里所有人的日历，然后下周找一个大家都合适的时间开一小时的讨论会 |![image.png](//sf3-cn.feishucdn.com/obj/open-platform-opendoc/e70fcac9e86e02ab31a1211517296cfa_aXCKBO04jm.png?height=803&lazyload=true&width=1280) | 

### 场景 4：会议数据分析

你知道自己每天在开会，但不知道时间到底花在了哪里。一句话，agent 拉取你过去两周的日历数据，自动给每场会议打标签（1:1/产品讨论/团队会/个人事务），写入多维表格，生成仪表盘。饼图看占比，柱状图看趋势，一张图告诉你该砍哪些会。

更进一步：agent 批量分析你的妙记，给每场会打一个"产出密度"分数，哪些会没有产出任何决策、哪些议题在重复讨论，直接帮团队减负。

| 用户输入提示词        | AI 自动分析         |
| --------- | --------------- |
| 拉取我过去两周的日历，把每个日程分类打标，写入多维表格，然后做一个仪表盘，我要看时间花在了哪里 |![image.png](//sf3-cn.feishucdn.com/obj/open-platform-opendoc/b09591354028ae30d93ba34cd2d99839_zCIhXq0R2l.png?height=1077&lazyload=true&maxWidth=350&width=1280) | 
| 分析我过去一个月所有的会议妙记，给每场会打个产出分数，告诉我哪些会建议砍掉 |![image.png](//sf3-cn.feishucdn.com/obj/open-platform-opendoc/6e84940ac8741facd5bdae3a32199656_2b8zj8I5E6.png?height=606&lazyload=true&maxWidth=300&width=938)<br>![image.png](//sf3-cn.feishucdn.com/obj/open-platform-opendoc/2dbf214cedc4ba11af2a53f7141f9abf_lioVNC2c8u.png?height=1624&lazyload=true&maxWidth=350&width=2836) | 

### 场景 5：未读邮件智能分类与处理

每天收几十封邮件，混杂着通知、审批、客户邮件，手动整理费时费力。

**用飞书 CLI 之后**：AI 定期扫描未读邮件，按优先级分类，重要邮件摘要推送到群聊，低优先级自动归档，还能帮每封邮件起草回复。
飞书 CLI 的邮箱能力做了重点增强，补齐了增删改查的完整能力，让飞书邮箱也能融入 AI 工作流。

| 用户输入提示词        | AI 自动处理        |
| --------- | --------------- |
| 查看我所有的未读邮件，重要邮件发摘要到 aurora 项目群，并给每封邮件写一个草稿回复。 |![image.png](//sf3-cn.feishucdn.com/obj/open-platform-opendoc/b89f7f24ac08449feccdd36c01a53619_kAC9qEAZ1B.png?height=803&lazyload=true&maxWidth=350&width=1280)<br> ![image.png](//sf3-cn.feishucdn.com/obj/open-platform-opendoc/eb11f0b6efc42f75a56ed0d92ea40f46_8rvN6RsHt2.png?height=803&lazyload=true&maxWidth=350&width=1280) | 

## 飞书 CLI 能力地图

飞书 CLI 覆盖了核心业务域，为 AI 提供以下接口能力：

**业务域** | **能做什么**                              |
| ------- | ------------------------------------- |
| 消息与群组   | 搜索消息和群聊、发消息、回复话题、管理成员与表情回应、收发图片文件     |
| 云文档     | 创建文档、读取内容、更新正文、插入图片附件、搜索云文档           |
| 云空间     | 上传下载文件、整理目录、导入导出文档、管理权限、处理评论          |
| 电子表格    | 创建表格、读写单元格、批量追加、查找替换、筛选视图、导出下载        |
| 多维表格    | 管理数据表、字段、记录、视图、表单、仪表盘、自动化与权限角色        |
| 日历      | 查日程、约会议、查忙闲、推荐时间、预定会议室、回复邀约           |
| 视频会议    | 搜索会议、获取纪要和逐字稿、关联日程文档                  |
| 妙记      | 搜索妙记、下载音视频、获取总结待办章节                   |
| 邮箱      | 搜索、读取、起草、发送、回复、转发、归档邮件，管理文件夹标签规则      |
| 任务      | 创建任务、更新状态、拆分子任务、管理清单和协作成员             |
| 知识库     | 查询空间、管理成员、管理节点和文档层级                   |
| 通讯录     | 查询用户、搜索同事、查看部门                        |
| 幻灯片     | 创建演示文稿、读取页面内容、增删幻灯片                   |
| 画板      | 读取画板、导出图片、用 DSL/PlantUML/Mermaid 更新画板 |
| OKR     | 查看周期、管理目标与关键结果、维护对齐关系和量化指标            |
| 审批      | 查询审批实例、处理审批任务                         |
| 考勤      | 查询考勤打卡记录

## 常用认证与配置命令
执行 `lark-cli help` 可查看命令总览

| 操作目标       | 对应命令                                    |
| ---------- | --------------------------------------- |
| 初始化应用配置    | `lark-cli config init`                  |
| 登录（用户身份）   | `lark-cli auth login`                   |
| 查看当前登录状态   | `lark-cli auth status`                  |
| 检查当前已有权限   | `lark-cli auth check`                   |
| 为某个业务域申请权限 | `lark-cli auth login --domain <domain>` |
| 登出         | `lark-cli auth logout`

## 在 CLI 中配置多应用

本节面向需要在本地同时运行多个飞书智能体的开发者。

### 第一步：创建多个 Profile（飞书应用）

####  方式一：交互式（推荐）

```bash
lark-cli config init --new --name bot-reader
```

> 每次带 `--name` 是追加，不带则覆盖默认 profile。

####  方式二：非交互式（自动化场景）

- 非交互式添加第一个 app：

```bash
  echo "YOUR_APP_SECRET" | lark-cli profile add \
    --name bot-reader \
    --app-id cli_xxxxxxxxxxxx \
    --app-secret-stdin
  ```

- 添加第二个 app：

```bash
  echo "YOUR_APP_SECRET_2" | lark-cli profile add \
    --name bot-writer \
    --app-id cli_yyyyyyyyyyyy \
    --app-secret-stdin
  ```

### 第二步：查看所有 Profile

```bash
lark-cli profile list
```

输出示例：

```json
[
  { "name": "bot-reader", "appId": "cli_xxx", "brand": "feishu", "active": true, "user": "张三", "tokenStatus": "valid" },
  { "name": "bot-writer", "appId": "cli_yyy", "brand": "feishu", "active": false, "user": "张三", "tokenStatus": "valid" }
]
```

`active: true` 是当前默认 profile。

### 第三步：使用 Profile

- 场景 1：全局切换默认 Profile：当调用 cli 时候不带 `--name` 则按照默认 profile 处理

```bash
lark-cli profile use bot-reader
```

- 场景 2：调用 cli 命令时传入 `--profile` 全局 flag。只在当前命令调用时按照该 profile（飞书应用调用），多进程并发安全。

```bash
lark-cli --profile bot-reader im send-message --chat-id oc_xxx --text "来自 reader bot"
lark-cli --profile bot-writer docs +create --api-version v2 --title "测试文档"
```

### Profile 管理命令速查

命令            | 说明                    |
| ------------------ | --------------------- |
| `lark-cli profile list`               | 查看所有 profile          |
| `lark-cli profile add --name <n> ...` | 添加新 profile           |
| `lark-cli profile rename <old> <new>` | 重命名                   |
| `lark-cli profile remove <name>`      | 删除（清空 token 和配置）      |
| `lark-cli profile use <name>`         | 切换默认 profile（写磁盘持久化）  |
| `lark-cli --profile <name> <命令>`      | 运行时指定 profile（并发场景必用）

## 常见问题

- **企业管理员有办法去控制权限吗？**

CLI 只是提供一键创建应用的能力，应用的管控仍然 follow 企业统一管控规则。

- **安装后提示命令不存在？**

确认 CLI 所在目录已加入系统 PATH。npm 安装可执行 `npm root -g` 查看全局目录。

- **授权失败，提示"授权码已过期"？**

OAuth 授权码有效期只有几分钟，超时后重新执行 `auth login` 即可。

- **调用 API 提示权限不足？**

根据报错提示补充授权：`auth login --scope "<missing_scope>"`。CLI 会告诉你缺少什么权限，并提供申请链接。应用身份调用还需在飞书开放平台后台开通对应权限。

- **如何在自动化任务或 AI 工作流中使用？**

先在本地完成一次配置和授权，然后把 CLI 接入脚本或 AI Agent 平台即可复用。

- **CLI 和 OpenClaw 飞书官方插件是什么关系？** 

飞书在 OpenClaw 等平台上的官方插件，底层就是基于这套 CLI 构建的。如果你已经在用飞书插件，不需要再单独安装 CLI——直接用就行。插件的能力会很快和 CLI 对齐。

- **支持国际版 Lark 吗？**

支持。通过 `config init` 并配置国际版 Lark 的应用即可使用。

- **如何获取帮助？**

执行 `lark-cli help` 查看命令总览，`lark-cli <command> --help` 查看具体用法，`schema` 命令可快速查询接口详情。

## 互助交流群

![image.png](//sf3-cn.feishucdn.com/obj/open-platform-opendoc/2646a8e17abed0f19c30efc26d1000c4_w56OFktmHO.png?height=522&lazyload=true&maxWidth=160&width=528)

## ⛲️许愿池

想让 CLI 支持什么新能力？在这里许个愿吧。你可以提交自己的需求，也可以给别人的愿望 +1。我们会定期查看并回复，票数高的需求会优先安排。你的每一票都在影响我们的迭代计划 💗

- 👉 [点击填表许愿](https://bytedance.larkoffice.com/share/base/form/shrcnFYECazRm9hPygXwLkEhmKf?prefill_%E6%A8%A1%E5%9D%97=CLI)
- 进入[投票表格](https://bytedance.larkoffice.com/base/Ebxvb6usfakMENs2GHIcL5Ern2f?table=tbl3HAHYqRF0ZSM6&view=vewUF0arsE)，点击 **我要 +1** 为你感同身受的许愿投票 